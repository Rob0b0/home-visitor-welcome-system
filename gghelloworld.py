import face_recognition
import cv2
import time
import boto3
from botocore.exceptions import ClientError
from botocore.vendored import requests
import logging
from threading import Thread, Event
import os
import json
import numpy as np
import awscam
import greengrasssdk

AWS_REGION = "us-east-1"
SENDER_EMAIL = "YOUR EMAIL"
RECEIVER_EMAIL = "YOUR ANOTHER EMAIL"
AUTHEN_TOKEN = 'your lighitng authen token'
VISITOR_PRESET = "your visitor lighting scene ID"

class LocalDisplay(Thread):
    """ Class for facilitating the local display of inference results
        (as images). The class is designed to run on its own thread. In
        particular the class dumps the inference results into a FIFO
        located in the tmp directory (which lambda has access to). The
        results can be rendered using mplayer by typing:
        mplayer -demuxer lavf -lavfdopts format=mjpeg:probesize=32 /tmp/results.mjpeg
    """
    def __init__(self, resolution):
        """ resolution - Desired resolution of the project stream """
        # Initialize the base class, so that the object can run on its own
        # thread.
        super(LocalDisplay, self).__init__()
        # List of valid resolutions
        RESOLUTION = {'1080p' : (1920, 1080), '720p' : (1280, 720), '480p' : (858, 480)}
        if resolution not in RESOLUTION:
            raise Exception("Invalid resolution")
        self.resolution = RESOLUTION[resolution]
        # Initialize the default image to be a white canvas. Clients
        # will update the image when ready.
        self.frame = cv2.imencode('.jpg', 255*np.ones([640, 480, 3]))[1]
        self.stop_request = Event()

    def run(self):
        """ Overridden method that continually dumps images to the desired
            FIFO file.
        """
        # Path to the FIFO file. The lambda only has permissions to the tmp
        # directory. Pointing to a FIFO file in another directory
        # will cause the lambda to crash.
        result_path = '/tmp/results.mjpeg'
        # Create the FIFO file if it doesn't exist.
        if not os.path.exists(result_path):
            os.mkfifo(result_path)
        # This call will block until a consumer is available
        with open(result_path, 'w') as fifo_file:
            while not self.stop_request.isSet():
                try:
                    # Write the data to the FIFO file. This call will block
                    # meaning the code will come to a halt here until a consumer
                    # is available.
                    fifo_file.write(self.frame.tobytes())
                except IOError:
                    continue

    def set_frame_data(self, frame):
        """ Method updates the image data. This currently encodes the
            numpy array to jpg but can be modified to support other encodings.
            frame - Numpy array containing the image data of the next frame
                    in the project stream.
        """
        ret, jpeg = cv2.imencode('.jpg', cv2.resize(frame, self.resolution))
        if not ret:
            raise Exception('Failed to set frame data')
        self.frame = jpeg

    def join(self):
        self.stop_request.set()

# if num_stranger > 0, use the message
def sesMessage(nameToPic, namesGot, hasVisitors):
    SENDER = "HVMS-Ultimate <"+SENDER_EMAIL">"
    RECIPIENT = RECIPIENT_EMAIL
    # The subject line for the email.
    SUBJECT = "Welcome Home Message"
    # name string for the names
    nameString = ""
    names = list(nameToPic.keys())
    for name in namesGot:
        nameString += name
    if hasVisitors:
        if len(namesGot) == 0:
            nameString += "new visitor(s)"
        else:
            nameString += " and new visitor(s)"
    # photos string for appending links
    photoString = ""
    for name, photo in nameToPic.items():
        photolink = "https://s3.amazonaws.com/home-visitor-tracker/{}".format(photo)
        photoString += "<a href={}>{}</a>\n".format(
                photolink, name
        )
    # The email body for recipients with non-HTML email clients.
    BODY_TEXT = ("Home Visitor Management System\r\n"
                "Welcome, Robert Chen!\n"
                "AWS SDK for Python (Boto)."
                )
                
    # The HTML body of the email.
    BODY_HTML = """<html>
    <head></head>
    <body>
    <p> Welcome, {}! </p>
    <p> Here is your faceshots when you entered home today:\n
       {}</p>
        <hr>
    <h3>Home Visitor Management System</h3>
    <p>This email was sent with
        <a href='https://aws.amazon.com/ses/'>Amazon SES</a> using the
        <a href='https://aws.amazon.com/sdk-for-python/'>
        AWS SDK for Python (Boto)</a>.</p>
    </body>
    </html>
                """            
    BODY_HTML_FINAL = BODY_HTML.format(nameString, photoString)
    # The character encoding for the email.
    CHARSET = "UTF-8"

    # Create a new SES resource and specify a region.
    client = boto3.client('ses',region_name=AWS_REGION)
    # Try to send the email.
    try:
        #Provide the contents of the email.
        response = client.send_email(
            Destination={
                'ToAddresses': [
                    RECIPIENT,
                ],
            },
            Message={
                'Body': {
                    'Html': {
                        'Charset': CHARSET,
                        'Data': BODY_HTML_FINAL,
                    },
                    'Text': {
                        'Charset': CHARSET,
                        'Data': BODY_TEXT,
                    },
                },
                'Subject': {
                    'Charset': CHARSET,
                    'Data': SUBJECT,
                },
            },
            Source=SENDER,
            # If you are not using a configuration set, comment or delete the
            # following line
            # ConfigurationSetName=CONFIGURATION_SET,
        )
    # Display an error if something goes wrong.	
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])

def activateScene(sceneID):
    token = AUTHEN_TOKEN
    sceneid = sceneID
    headers = {
    "Authorization": "Bearer %s" % token,
    }
    response = requests.put('https://api.lifx.com/v1/scenes/scene_id:%s/activate' % sceneid, headers=headers)
    print("lighting request sent")

s3 = boto3.resource('s3')
def function_handler(lient, userdata, message):
    # Create an IoT client for sending to messages to the cloud.
    client = greengrasssdk.client('iot-data')
    iot_topic = '$aws/things/{}/infer'.format(os.environ['AWS_IOT_THING_NAME'])
    # Create a local display instance that will dump the image bytes to a FIFO
    # file that the image can be rendered locally.
    local_display = LocalDisplay('720p')
    local_display.start()
    # The height and width of the training set images
    input_height = 360
    input_width = 640

    # Create arrays of known face encodings and their names
    known_face_encodings = [
    ]
    known_face_files = [
    ]

    # Initialize some variables
    face_locations = []
    face_encodings = []
    face_names = []
    process_this_frame = True
    client.publish(topic=iot_topic, payload='going into the loop')
    timeout = time.time() + 5   # set a timeout period
    while True:
        # Only process every other frame of video to save time
        if process_this_frame:
            # Get a frame from the video stream
            ret, frame = awscam.getLastFrame()
            if not ret:
                raise Exception('Failed to get frame from the stream')
            # Resize frame of video to 1/4 size for faster face recognition processing
            small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)

            # Convert the image from BGR color (which OpenCV uses) to RGB color (which face_recognition uses)
            rgb_small_frame = small_frame[:, :, ::-1]

            # Find all the faces and face encodings in the current frame of video
            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            face_names = []
            for i in range(len(face_encodings)):
                face_encoding = face_encodings[i]
                # See if the face is a match for the known face(s)
                matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
                
                if not (True in matches):
                    # new face
                    # add face encoding to familiar face greoup
                    known_face_encodings.append(face_encoding)
                    # snapshot of the face
                    (top, right, bottom, left)=face_locations[i]
                    face_frame = frame[top*2:bottom*2, left*2:right*2]
                    known_face_files.append(face_frame)

        process_this_frame = not process_this_frame
        # Hit 'q' on the keyboard to quit!
        if (time.time() > timeout):
            break
    # export the images
    strangerNum = 1
    timestamp = time.time()
    for face in known_face_files:
        filename = "Stranger"+str(strangerNum)+".jpg"
        cv2.imwrite(filename, face)
        # add to s3
        response=s3.Bucket('home-visitor-tracker').upload_file(
            filename, str(timestamp)+'/'+filename,ExtraArgs={'ACL':'public-read'}
        )
        print("S3 upload response: {}".format(response))
        strangerNum +=1 
    print("{} strangers counted.".format(strangerNum))

    # only proceed if detect faces
    if strangerNum > 1:
        # dynamo db
        dynamodb = boto3.resource('dynamodb')
        face_table = dynamodb.Table('faces')
        # recognition part
        rekognition = boto3.client('rekognition')
        num_familiars = 0
        namesGot = []
        scenesGot = []
        nameToPic = {}
        num_realStranger = 0
        for i in range(1, strangerNum):
            # search familliar faces for each one
            imageName = str(timestamp)+'/'+"Stranger"+str(i)+".jpg"
            response = rekognition.search_faces_by_image(
                CollectionId='familiars',
                FaceMatchThreshold=85,
                Image={
                    'S3Object': {
                        'Bucket': 'home-visitor-tracker',
                        'Name': imageName,
                    },
                },
                MaxFaces=1,
            )
            print("Rekognition Response: {}".format(response))
            if len(response['FaceMatches'])>0:
                #match
                num_familiars += 1
                # dynamo db retrieve scene and name
                response  = face_table.get_item(
                    Key={
                        'faceID': response['FaceMatches'][0]['Face']['FaceId']
                    }
                )
                print("DynamoDB Response: {}".format(response))
                item = response['Item']
                namesGot.append(item['Name'])
                # add to name->pic dict
                nameToPic[item['Name']] = imageName
                scenesGot.append(item['SceneID'])
            else:
                num_realStranger += 1
                nameToPic['New Face {}'.format(num_realStranger)]=imageName
        
        if num_familiars == strangerNum-1:
            # for now, randomly select scene from familiars
            sceneSelected = scenesGot[0]
            # activate lighting
            activateScene(sceneSelected)
            # send email
            sesMessage(nameToPic, namesGot, False)
        else:
            # use visitor preset
            sceneSelected = VISITOR_PRESET
            # activate lighting
            activateScene(sceneSelected)
            # send email
            sesMessage(nameToPic, namesGot, True)

import face_recognition
import cv2
import time
import boto3
from botocore.exceptions import ClientError
from botocore.vendored import requests
import logging
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

AWS_REGION = "us-east-1"

# if num_stranger > 0, use the message
def sesMessage(nameToPic, namesGot, hasVisitors):
    SENDER = "HVMS-Ultimate <rchenyb@gmail.com>"
    RECIPIENT = "lord0robert@gmail.com"
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
    token = 'cba17032fb0c5a1c28595c855d5e88afb52dae32377d171e90c1f69bd2bd2a18'
    sceneid = sceneID
    headers = {
    "Authorization": "Bearer %s" % token,
    }
    response = requests.put('https://api.lifx.com/v1/scenes/scene_id:%s/activate' % sceneid, headers=headers)
    print("lighting request sent")

s3 = boto3.resource('s3')
def function_handler(lient, userdata, message):
    # Get a reference to webcam #0 (the default one)
    video_capture = cv2.VideoCapture(0)

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
    timeout = time.time() + 5   # set a timeout period
    while True:
        # Grab a single frame of video
        ret, frame = video_capture.read()
        # Only process every other frame of video to save time
        if process_this_frame:
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
        #cv2.imshow('Video', frame)
        # Hit 'q' on the keyboard to quit!
        if (time.time() > timeout) or (cv2.waitKey(1) & 0xFF == ord('q')):
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
    # Release handle to the webcam
    video_capture.release()
    cv2.destroyAllWindows()

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
            sceneSelected = '4c1672db-0eb4-450a-b939-1308cb136a38'
            # activate lighting
            activateScene(sceneSelected)
            # send email
            sesMessage(nameToPic, namesGot, True)

myMQTTClient = None
myMQTTClient = AWSIoTMQTTClient("MacRob")
myMQTTClient.configureEndpoint(
    "a2prn2xi1zplck-ats.iot.us-east-1.amazonaws.com", 8883)
myMQTTClient.configureCredentials(
    "thing/AmazonRootCA1.pem", 
    "thing/c89e4e3a2a-private.pem.key", 
    "thing/c89e4e3a2a-certificate.pem.crt")

# logger = logging.getLogger("AWSIoTPythonSDK.core")
# logger.setLevel(logging.DEBUG)
# streamHandler = logging.StreamHandler()
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# streamHandler.setFormatter(formatter)
# logger.addHandler(streamHandler)

myMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
myMQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
myMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
myMQTTClient.configureConnectDisconnectTimeout(10)  # 10 sec
myMQTTClient.configureMQTTOperationTimeout(5)  # 5 sec
# connect to topic
myMQTTClient.connect()
myMQTTClient.subscribe("iotbutton/G030JF05327510BA", 1, function_handler)
print("listening on topic iotbutton/G030JF05327510BA")
while True:
    continue

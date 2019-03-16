# Home Visitor Welcome System
### Author: Robert (Yunbo) Chen

## Setup: 
There is only one Lambda function needed for actual code. 
But you need to set up different AWS services which I will walk you through.

__Headsup__: 
 * I used an AWS DeepLens as the greegrass device. But any Raspberry Pi or Arduino is feasible for this. 
 * Use us-east-1 as the region since for some of my code I may directly used "us-east-1" as the region.



1. Set up S3   
    1. Create a bucket called "home-visitor-tracker" to sync with the name in the code.
    
4. Set up Rekognition
    1. Download and install AWS-CLI, and do `aws configure` to configure your aws-cli.
    2. Create a Rekognition collection by doing 
        ```
        aws rekognition create-collection \
        --collection-id "collectionname"
        ```
    3. Upload your desired known faces images onto specific S3 bucket.
    4. index faces by doing 
        ```
        aws rekognition index-faces \
        --image '{"S3Object":{"Bucket":"bucket-name","Name":"file-name"}}' \
        --collection-id "collection-id" \
        --max-faces 1 \
        --quality-filter "AUTO" \
        --detection-attributes "ALL" \
         --external-image-id "example-image.jpg" 
        ```
        on each face image.

5. Set up your lighting scene  
    1. I am using LIFX lighting, it can be done by creating different scenes on the mobile app.
    2. Get your authentication token by setting up your LIFX account online.
    2. On the terminal do 
        ```
        curl"https://api.lifx.com/v1/scenes"      -H "Authorization: Bearer your_authenitcation_token"
        ```
        to retrieve your sceneIDs.
5. Set up DynamoDB  
    1. Create a table with primary key of `faceID`
    2. populate your table with the `faceID`, `full name`, and `sceneID`

7. Set up SES
    1. Really easy, just have the two email addresses verified.

1. Set up Lambda 
    1. Create the lambda function with the name "gghelloworld" 

    1. Set the Python environment to be 3.6 or 3.7

    2. Set the handler name to be `gghelloworld.function_handler`.

    3. Click the "action" tab on the top and click "export the function" to download the function as a zip file.

    4. Extract the zip file to get the root function folder.

    5. Replace the original `gghelloworld.py` with the file in the `CloudCode` folder.

    6. Change the email address with your own emails set previously.

    7. Change the authentication token to the own your got from LIFX.

    8. Change the sceneID to the visitor sceneID you set on the mobile phone.

    6. Then open the terminal, at the file folder, set up a virtual environment.

    7. Then in the environment, do 

        ```
        mkdir package
        pip install face-recognition --target .
        ```

        then wait for it to complete and propagate the folder with required packages.

    8. Then put the rest of the greengrass package folders into the package folder.

    9. In the package folder, do `zip -r9 ../function.zip .`

    10. Go to the root folder, do `zip -g function.zip function.py`

    11. Upload the zip file to the lambda function, you may need to use S3 to upload it.
    12. Set the timeout interval to be 6 seconds.
    13. Set the environment variable `AWS_IOT_THING_NAME` with your iot thing id of the greegrass device
    13. For the trigger, use AWS IoT, and in the configuration part, select *IoT Button* and then configure your IoT button to register it on the cloud.

2. Set up greengrass core. 
    1. Create a greegrass group.
    2. Add the lambda function `gghelloworld` to the lambda tab.
    3. Add a subscription from IoT Cloud to the lambda function, with the topic of your IoT Button topic.
    4. Deploy the greengrass function to your device.
    
7. Now you should be able to use the IoT button to trigger your lambda function deployed on the greengrass core with a camera, and see the light turns to your desired scene and receive an notification email. 
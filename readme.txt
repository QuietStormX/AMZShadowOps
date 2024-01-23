How to run the script
1. first make sure multilogin is running.
2. create a .env file the example for it is in .example.env. Make sure to change the machine name in it to the one it is being used on.
3. for multilogin6 match the port number in the script with multilogin6 api https://help.multilogin.com/api-desktop/cli-and-local-api?from_search=135442315#:~:text=Local%20API%20endpoints-,Multilogin%20port%20allocation,-You%20need%20to (multiloginapp.port=35111)
4. First according to the machine it is being ran on download the batch from the tab https://docs.google.com/spreadsheets/d/1rsmvosoGr-Wmgg2wsaeaMbWvrvVlJk9bx_A_L_AaK4o/edit#gid=1598892673 and rename the file to input.csv and place it in the root folder of the script
5. to run the multilogin6 where each review is reported one time run the fmain.py
6. to run the multiloginx where each review is reported one time run the fmainx.py
7. to run the multiloginx where each review is reported 3 times by three different profiles run the fmainx3.py

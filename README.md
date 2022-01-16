Little script for checking hosts for alive via ping and HTTP/HTTPS requests with notification by email.

Requirements: 
   * python3
   * python packages: 
     * requests 
     * pythonping
     * watchdog
       
To install python packages execute:
```
pip3 install requests pythonping watchdog
```

Copy **watch.sample.ini** to **watch.ini**.
```
cp watch.sample.ini watch.ini
```

Edit **watch.ini**. Follow hints in comments.

Run script:
```
python3 watch.py
```

STDOUT example:
```
2022-01-17 04:31:48 [INFO] 8.8.8.8 PING OK
2022-01-17 04:31:48 [INFO] google.com PING OK
2022-01-17 04:31:48 [INFO] google.com HTTP OK
2022-01-17 04:31:49 [INFO] youtube.com HTTP OK
2022-01-17 04:31:50 [INFO] instagram.com HTTPS OK
2022-01-17 04:31:50 [INFO] facebook.com HTTPS OK
```
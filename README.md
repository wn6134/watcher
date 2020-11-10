Little script for checking hosts for alive via ping and HTTP/HTTPS requests with notification by email.

Requirements: 
   * python3
   * python packages: 
     * requests 
     * pythonping
       
To install python packages execute:
```
pip3 install requests pythonping
```

Edit **watch.ini**. Follow hints in comments.

Run script:
```
python3 watch.py
```

STDOUT example:
```
2020-11-09 19:54:18 [INFO] Ping test 8.8.8.8 OK
2020-11-09 19:54:18 [INFO] Ping test google.com OK
2020-11-09 19:54:18 [INFO] HTTP test google.com OK
2020-11-09 19:54:19 [INFO] HTTP test youtube.com OK
2020-11-09 19:54:20 [INFO] HTTPS test instagram.com OK
2020-11-09 19:54:20 [INFO] HTTPS test facebook.com OK
2020-11-09 19:54:25 [INFO] Ping test 8.8.8.8 OK
2020-11-09 19:54:25 [INFO] Ping test google.com OK
2020-11-09 19:54:25 [INFO] HTTP test google.com OK
2020-11-09 19:54:26 [INFO] HTTP test youtube.com OK
2020-11-09 19:54:27 [INFO] HTTPS test instagram.com OK
2020-11-09 19:54:27 [INFO] HTTPS test facebook.com OK
2020-11-09 19:54:32 [INFO] All tests OK
```
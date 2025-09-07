NOTE: Names and descriptions of all files, with Detailed instructions for compiling and running the client and server
programs are given below.

//////////////////////
TCP
////////////////////////

1.TCP_loan_client.py
////////////////////////
This client will Take input from the user (loan amount, loan term, and interest rate).
Send this data to the server using TCP sockets.
Receive the monthly payment and total payment from the server.
Display the results to the user.

////////////////////////
2.TCP_loan_server.py
////////////////////////
This server will Listen for connections from clients.
For each connection, receive the loan data, compute the monthly and total payments, and send the result back to the client.

////////////////////////
HOW TO RUN TCP:
////////////////////////
Start the server:
On your terminal, run: python TCP_loan_server.py
On another terminal, Run the client, run:
python TCP_loan_client.py interactive

from interactive you can provide further inputs based on your requirements like
LOAN Phoenix 150000 30 4.5
LOAN <username> <amount> <years> <rate>

//COMMENT:  I ran both client and server on same machine so, i used localhost: python TCP_loan_server.py 127.0.0.1 13000
//COMMENT:  Note: if you ran both client and server on same machine, use YOUR localhost
where as 127.0.0.1 is localhost/loopback IP address FOR MY MACHINE.

////////////////////////////////////////////////////
If client and server running on different machines:
////////////////////////////////////////////////////
Start the server:
On your terminal, run: python TCP_loan_server.py --host 0.0.0.0 --port 13000
Note the server machine’s IP address on the network.
On Windows you can check with powershell: ipconfig

Run the client:
On another terminal, run:
python TCP_loan_client.py --host <server_ip> --port <port_no> interactive

For example: python TCP_loan_client.py --host 192.168.1.25 --port 13000 interactive
or one-shot:
python TCP_loan_client.py loan Phoenix 150000 30 4.5 --host 192.168.1.25 --port 13000
///////////////////////////////////////////////////

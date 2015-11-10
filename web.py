import errno
import select
import socket
import sys
import traceback
import argparse
import os
from time import gmtime, strftime
from datetime import datetime


configHost = {}
configMedia = {}
configParameter = {}

'''Parse Config File Function'''
def parseConfig():
    Debug.dprint("SERVER::parseConfig()")

    fileReader = open("web.conf", 'r')
    #print fileReader.read()
    for line in fileReader.read().split('\n'):
        items = line.split(' ')
        if items[0] == "host":
            configHost[items[1]] = items[2]
        elif items[0] == "media":
            configMedia[items[1]] = items[2]
        elif items[0] == "parameter":
            configParameter[items[1]] = items[2]



"""Debug Class"""
class Debug:
    debugState = False

    @staticmethod
    def setState(newState):
        Debug.debugState = newState

    @staticmethod
    def dprint(stringToPrint):
        if(Debug.debugState == True):
            print '\t' + str(stringToPrint)






class Poller:
    """ Polling server """
    def __init__(self,port):
        self.host = ""
        self.port = port
        self.open_socket()
        self.clients = {}
        self.timestamps = {}
        self.caches = {}
        self.size = 1024

    def open_socket(self):
        Debug.dprint("POLLER::open_socket")
        """ Setup the socket for incoming clients """
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
            self.server.bind((self.host,self.port))
            self.server.listen(5)
            self.server.setblocking(0)
        except socket.error, (value,message):
            if self.server:
                self.server.close()
            print "Could not open socket: " + message
            sys.exit(1)





    def run(self):
        Debug.dprint("POLLER::run")
        """ Use poll() to handle each incoming client."""
        self.poller = select.epoll()
        self.pollmask = select.EPOLLIN | select.EPOLLHUP | select.EPOLLERR
        self.poller.register(self.server,self.pollmask)
        while True:
            # poll sockets
            try:
                for key in self.clients:
                    lastEvent = self.timestamps[key]
                    if lastEvent != 0:
                        current = datetime.now()
                        totalTime = current - lastEvent
                        if (totalTime.seconds >= configParameter['timeout']):
                            Debug.dprint("POLLER::run:mark&sweep:timout_occured")
                            self.poller.unregister(key)
                            self.clients[key].close()
                            del self.clients[key]
                            del self.timestamps[key]

                fds = self.poller.poll(timeout=0.5)

            except:
                return
            for (fd,event) in fds:
                # handle errors
                if event & (select.POLLHUP | select.POLLERR):
                    self.handleError(fd)
                    continue
                # handle the server socket
                if fd == self.server.fileno():
                    self.handleServer()
                    continue
                # handle client socket
                result = self.handleClient(fd)






    def handleError(self,fd):
        Debug.dprint("POLLER::handleError")
        self.poller.unregister(fd)
        if fd == self.server.fileno():
            # recreate server socket
            self.server.close()
            self.open_socket()
            self.poller.register(self.server,self.pollmask)
        else:
            # close the socket
            self.clients[fd].close()
            del self.clients[fd]







    def handleServer(self):
        # accept as many clients as possible
        Debug.dprint("POLLER::handleServer")
        while True:
            try:
                (client,address) = self.server.accept()
            except socket.error, (value,message):
                # if socket blocks because no clients are available,
                # then return
                Debug.dprint("POLLER::handleServer:socket_exception")
                if value == errno.EAGAIN or errno.EWOULDBLOCK:
                    return
                print traceback.format_exc()
                sys.exit()
            # set client socket to be non blocking
            client.setblocking(0)
            self.clients[client.fileno()] = client
            self.timestamps[client.fileno()] = 0
            self.poller.register(client.fileno(),self.pollmask)









    def handleClient(self,fd):
        Debug.dprint("-\n-\n********   NEW CLIENT   ********\n-\n-\n")
        Debug.dprint("POLLER::handleClient:fd->" + str(fd))
        try:
            data = self.clients[fd].recv(self.size)
            self.timestamps[fd] = datetime.now()
            Debug.dprint("POLLER::handleClient:data\n" + str(data))

        except socket.error, (value,message):
            # if no data is available, move on to another client
            if value == errno.EAGAIN or errno.EWOULDBLOCK:
                return
            print traceback.format_exc()
            sys.exit()

        if data:
            #if there is data 
            #create a response
            response = self.handleRequest(data)
            #send the response
            self.clients[fd].send(response)
        else:
            self.poller.unregister(fd)
            self.clients[fd].close()
            del self.clients[fd]





    def handleRequest(self, data):
        #should only get here if the request is completed to the double line return
        Debug.dprint("POLLER::handleRequest:data->" + str(data) + "<-data")
        #create and serve the clients request
        self.respHeaders = {}
        self.respHeaders['Server'] = "SimpleHTTP/0.6 Python/2.7.9"
        self.respHeaders['Date'] = strftime("%a, %d %b %Y %H:%M:%S GMT", gmtime())

        #parse the data (GET header)
        try:
            from http_parser.parser import HttpParser
        except ImportError:
            from http_parser.pyparser import HttpParser

        p = HttpParser()
        nparsed = p.execute(data,len(data))

        #print basic debug from http parser
        Debug.dprint("POLLER::handleRequest:HttpParser:get_method()->" + p.get_method())
        Debug.dprint("POLLER::handleRequest:HttpParser:get_path()->" + p.get_path())
        Debug.dprint("POLLER::handleRequest:HttpParser:get_headers()\n")
        dataHeaders = p.get_headers()
        for i in dataHeaders:
            Debug.dprint(i + ":" + dataHeaders[i])

        #assign from http parser, headers grabbed previously
        method = p.get_method();
        path = p.get_path();




        #check for GET, if not return 501
        if method != 'GET':
            return self.code501();





        #identify host
        if dataHeaders.has_key('Host'):
            #if a host key is present
            Debug.dprint("POLLER::handleRequest:Host->" + dataHeaders['Host'])
            #check for the host key in the config dictionary
            if configHost.has_key(dataHeaders['Host']):
                #if the specified host is in the config dictionary, make the root directory the path assiated with requested host
                rootDir = configHost[dataHeaders['Host']]
            else:
                #if the specified host is not in the config dictionary, set to default??? THIS MAY NEED TO BE AN ERROR
                rootDir = configHost['default']
        else:
            #if a host key is not present
            rootDir = configHost['default']





        #identify requested file
        #for the case of an empty path, point to index
        if path =="/":
            #if the path is blank, set the path to index.html
            path = "/index.html"

        #attempt to retreive the file
        try:
            #identify the type of file
            fileType = ""
            if path.find('.') != -1:
                #split at the file extention period and isolate the filetype
                pathSplit = path.split('.')
                fileType = str(pathSplit[len(pathSplit) - 1])
                Debug.dprint("POLLER::handleRequest:fileType->" + str(fileType));

            #assign a MIME type from the condif dictionary
            if configMedia.has_key(fileType):
                self.respHeaders['Content-Type'] = configMedia[fileType]
            else:
                self.respHeaders['Content-Type'] = "test/plain"

            #check if the file excists, if not throw code 404
            #create filepath
            filePath = rootDir + path
            Debug.dprint("POLLER::handleRequest:filePath->" + str(filePath));
            if not os.path.isfile(filePath):
                return self.code404()

            #check for permissions, if not throw code 403
            if not os.access(filePath, os.R_OK):
                return self.code403()

            #read file as binary into a body variable
            fileReader = open(filePath, 'rb')
            respBody = fileReader.read()

        except IOError:
            return self.code500()


        #if everything worked, package response and return
        self.respHeaders['Content-Length'] = os.stat(filePath).st_size
        self.respHeaders['Last-Modified'] = strftime("%a, %d %b %Y %H:%M:%S GMT", gmtime(os.stat(filePath).st_mtime))

        response = "HTTP/1.1 200 OK\r\n"

        for key in self.respHeaders:
            response += str(key) + ": " + str(self.respHeaders[key]) + "\r\n"
            Debug.dprint("POLLER::responseHeader: " + str(key) + ": " + str(self.respHeaders[key]))

        response += "\r\n"
        response += str(respBody)
        return response







        

    def code400(self):
        Debug.dprint("POLLER::code400()")
        #Return 400 Bad Request response

        body = "<h1>400 Bad Request</h1>"
        self.respHeaders['Content-Length'] = len(body)
        self.respHeaders['Content-type'] = "text/html"
        response = "HTTP/1.1 400 Bad Request\r\n"

        for key in self.respHeaders:
            response += str(key) + ": " + str(self.respHeaders[key]) + "\r\n"
        response += "\r\n" + body

        return response

    def code403(self):
        Debug.dprint("POLLER::code403()")
        #Return 403 Forbidden response

        body = "<h1>403 Forbidden</h1>"
        self.respHeaders['Content-Length'] = len(body)
        self.respHeaders['Content-Type'] = "text/html"
        response = "HTTP/1.1 403 Forbidden\r\n"

        for key in self.respHeaders:
            response += str(key) + ": " + str(self.respHeaders[key]) + "\r\n"
        response += "\r\n" + body

        return response

    def code404(self):
        Debug.dprint("POLLER::code404()")
        #Retrurn 404 Not Found response

        body = "<h1>404 Not Found</h1>"
        self.respHeaders['Content-Length'] = len(body)
        self.respHeaders['Content-Type'] = "text/html"
        response = "HTTP/1.1 404 Not Found\r\n"

        for key in self.respHeaders:
            response += str(key) + ": " + str(self.respHeaders[key]) + "\r\n"
        response += "\r\n" + body

        return response

    def code500(self):
        Debug.dprint("POLLER::code500()")
        #Return 500 Internal Server Error response

        body = "<h1>500 Internal Server Error</h1>"
        self.respHeaders['Content-Length'] = len(body)
        self.respHeaders['Content-Type'] = "text/html"
        response = "HTTP/1.1 500 Internal Server Error\r\n"

        for key in self.respHeaders:
            response += str(key) + ": " + str(self.respHeaders[key]) + "\r\n"
        response += "\r\n" + body

        return response

    def code501(self):
        Debug.dprint("POLLER::code501()")
        #Return 501 Not Implemented response

        body = "<h1>501 Not Implemented</h1>"
        self.respHeaders['Content-Length'] = len(body)
        self.respHeaders['Content-Type'] = "text/html"
        response = "HTTP/1.1 501 Not Implemented\r\n"

        for key in self.respHeaders:
            response += str(key) + ": " + str(self.respHeaders[key]) + "\r\n"
        response += "\r\n" + body

        return response




class Main:
    """ Parse command line options and perform the download. """
    def __init__(self):
        self.parse_arguments()

    def parse_arguments(self):
        ''' parse arguments, which include '-p' for port '''
        parser = argparse.ArgumentParser(prog='Echo Server', description='A simple echo server that handles one client at a time', add_help=True)
        parser.add_argument('-p', '--port', type=int, action='store', help='port the server will bind to',default=8080)
        parser.add_argument('-d', action='store_true')
        self.args = parser.parse_args()

    def run(self):
        p = Poller(self.args.port)
        Debug.setState(self.args.d)
        parseConfig()
        p.run()





if __name__ == "__main__":
    m = Main()
    m.parse_arguments()

    print m.args.d

    try:
        m.run()
    except KeyboardInterrupt:
        pass
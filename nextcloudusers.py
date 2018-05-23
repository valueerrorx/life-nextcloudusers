#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os
from PyQt5 import QtCore, uic, QtWidgets
from PyQt5.QtGui import *

import subprocess
import time
import re
import datetime
import requests
import xml.etree.ElementTree as ET
import six
from six.moves.urllib import parse


USER = subprocess.check_output("logname", shell=True).rstrip().decode("utf-8")
USER_HOME_DIR = os.path.join("/home", str(USER))





class ResponseError(Exception):
    def __init__(self, res, errorType):
        if type(res) is int:
            code = res
        else:
            code = res.status_code
            self.res = res
        Exception.__init__(self, errorType + " error: %i" % code)
        self.status_code = code

    def get_resource_body(self):
        if self.res is not None:
            return self.res.content
        else:
            return None


class OCSResponseError(ResponseError):
    def __init__(self, res):
        ResponseError.__init__(self, res, "OCS")

    def get_resource_body(self):
        if self.res is not None:
            import xml.etree.ElementTree as ElementTree
            try:
                root_element = ElementTree.fromstringlist(self.res.content)
                if root_element.tag == 'message':
                    return root_element.text
            except ET.ParseError:
                return self.res.content
        else:
            return None


class HTTPResponseError(ResponseError):
    def __init__(self, res):
        ResponseError.__init__(self, res, "HTTP")













class Client(object):
    """nextCloud/ownCloud client"""

    OCS_BASEPATH = 'ocs/v1.php/'
    OCS_SERVICE_SHARE = 'apps/files_sharing/api/v1'
    OCS_SERVICE_PRIVATEDATA = 'privatedata'
    OCS_SERVICE_CLOUD = 'cloud'

    # constants from lib/public/constants.php
    OCS_PERMISSION_READ = 1
    OCS_PERMISSION_UPDATE = 2
    OCS_PERMISSION_CREATE = 4
    OCS_PERMISSION_DELETE = 8
    OCS_PERMISSION_SHARE = 16
    OCS_PERMISSION_ALL = 31
    # constants from lib/public/share.php
    OCS_SHARE_TYPE_USER = 0
    OCS_SHARE_TYPE_GROUP = 1
    OCS_SHARE_TYPE_LINK = 3
    OCS_SHARE_TYPE_REMOTE = 6

    def __init__(self, url, **kwargs):
        """Instantiates a client

        :param url: URL of the target nextCloud instance
        :param verify_certs: True (default) to verify SSL certificates, False otherwise
        :param dav_endpoint_version: None (default) to force using a specific endpoint version
        instead of relying on capabilities
        :param debug: set to True to print debugging messages to stdout, defaults to False
        """
        if not url.endswith('/'):
            url += '/'

        self.url = url
        self._session = None
        self._debug = kwargs.get('debug', False)
        self._verify_certs = kwargs.get('verify_certs', True)
   

        self._capabilities = None
        self._version = None

    def login(self, user_id, password):
        """Authenticate
        This will create a session on the server.

        :param user_id: user id
        :param password: password
        :raises: HTTPResponseError in case an HTTP error status was returned
        """
      

        self._session = requests.session()
        self._session.verify = self._verify_certs
        self._session.auth = (user_id, password)

        try:
            self._update_capabilities()

        except HTTPResponseError as e:
            self._session.close()
            self._session = None
            raise e
        

    def logout(self):
        """Log out the authenticated user and close the session.

        :returns: True if the operation succeeded, False otherwise
        :raises: HTTPResponseError in case an HTTP error status was returned
        """
        self._session.close()
        return True





    def create_user(self, user_name, initial_password):
        """Create a new user with an initial password via provisioning API.
        It is not an error, if the user already existed before.
        If you get back an error 999, then the provisioning API is not enabled.

        :param user_name:  name of user to be created
        :param initial_password:  password for user being created
        :returns: True on success
        :raises: HTTPResponseError in case an HTTP error status was returned

        """
        res = self._make_ocs_request(
            'POST',
            self.OCS_SERVICE_CLOUD,
            'users',
            data={'password': initial_password, 'userid': user_name}
        )

        # We get 200 when the user was just created.
        if res.status_code == 200:
            tree = ET.fromstring(res.content)
            self._check_ocs_status(tree, [100])
            return True

        raise HTTPResponseError(res)
    
    
    def user_exists(self, user_name):
        """Checks a user via provisioning API.
        If you get back an error 999, then the provisioning API is not enabled.

        :param user_name:  name of user to be checked
        :returns: True if user found

        """
        users = self.search_users(user_name)

        return user_name in users


    def search_users(self, user_name):
        """Searches for users via provisioning API.
        If you get back an error 999, then the provisioning API is not enabled.

        :param user_name:  name of user to be searched for
        :returns: list of usernames that contain user_name as substring
        :raises: HTTPResponseError in case an HTTP error status was returned

        """
        action_path = 'users'
        if user_name:
            action_path += '?search={}'.format(user_name)

        res = self._make_ocs_request(
            'GET',
            self.OCS_SERVICE_CLOUD,
            action_path
        )

        if res.status_code == 200:
            tree = ET.fromstring(res.content)
            users = [x.text for x in tree.findall('data/users/element')]

            return users

        raise HTTPResponseError(res)




    def add_user_to_group(self, user_name, group_name):
        """Adds a user to a group.

        :param user_name:  name of user to be added
        :param group_name:  name of group user is to be added to
        :returns: True if user added
        :raises: HTTPResponseError in case an HTTP error status was returned

        """

        res = self._make_ocs_request(
            'POST',
            self.OCS_SERVICE_CLOUD,
            'users/' + user_name + '/groups',
            data={'groupid': group_name}
        )

        if res.status_code == 200:
            tree = ET.fromstring(res.content)
            self._check_ocs_status(tree, [100])
            return True

        raise HTTPResponseError(res)



    def group_exists(self, group_name):
        """Checks a group via provisioning API.
        If you get back an error 999, then the provisioning API is not enabled.

        :param group_name:  name of group to be checked
        :returns: True if group exists
        :raises: HTTPResponseError in case an HTTP error status was returned

        """
        res = self._make_ocs_request(
            'GET',
            self.OCS_SERVICE_CLOUD,
            'groups?search=' + group_name
        )

        if res.status_code == 200:
            tree = ET.fromstring(res.content)

            for code_el in tree.findall('data/groups/element'):
                if code_el is not None and code_el.text == group_name:
                    return True

            return False

        raise HTTPResponseError(res)



    @staticmethod
    def _encode_string(s):
        """Encodes a unicode instance to utf-8. If a str is passed it will
        simply be returned

        :param s: str or unicode to encode
        :returns: encoded output as str
        """
        if six.PY2 and isinstance(s, unicode):
            return s.encode('utf-8')
        return s




    @staticmethod
    def _check_ocs_status(tree, accepted_codes=[100]):
        """Checks the status code of an OCS request

        :param tree: response parsed with elementtree
        :param accepted_codes: list of statuscodes we consider good. E.g. [100,102] can be used to accept a POST
               returning an 'already exists' condition
        :raises: HTTPResponseError if the http status is not 200, or OCSResponseError if the OCS status is not one of the accepted_codes.
        """
        code_el = tree.find('meta/statuscode')
        if code_el is not None and int(code_el.text) not in accepted_codes:
            r = requests.Response()
            msg_el = tree.find('meta/message')
            if msg_el is None:
                msg_el = tree  # fallback to the entire ocs response, if we find no message.
            r._content = ET.tostring(msg_el)
            r.status_code = int(code_el.text)
            raise OCSResponseError(r)


    def make_ocs_request(self, method, service, action, **kwargs):
        """Makes a OCS API request and analyses the response

        :param method: HTTP method
        :param service: service name
        :param action: action path
        :param \*\*kwargs: optional arguments that ``requests.Request.request`` accepts
        :returns :class:`requests.Response` instance
        """

        accepted_codes = kwargs.pop('accepted_codes', [100])

        res = self._make_ocs_request(method, service, action, **kwargs)
        if res.status_code == 200:
            tree = ET.fromstring(res.content)
            self._check_ocs_status(tree, accepted_codes=accepted_codes)
            return res

        raise OCSResponseError(res)


    def _make_ocs_request(self, method, service, action, **kwargs):
        """Makes a OCS API request

        :param method: HTTP method
        :param service: service name
        :param action: action path
        :param \*\*kwargs: optional arguments that ``requests.Request.request`` accepts
        :returns :class:`requests.Response` instance
        """
        slash = ''
        if service:
            slash = '/'
        path = self.OCS_BASEPATH + service + slash + action

        attributes = kwargs.copy()

        if 'headers' not in attributes:
            attributes['headers'] = {}

        attributes['headers']['OCS-APIREQUEST'] = 'true'

        if self._debug:
            print('OCS request: %s %s %s' % (method, self.url + path,
                                             attributes))

        res = self._session.request(method, self.url + path, **attributes)
        return res


    def _xml_to_dict(self, element):
        """
        Take an XML element, iterate over it and build a dict

        :param element: An xml.etree.ElementTree.Element, or a list of the same
        :returns: A dictionary
        """
        return_dict = {}
        for el in element:
            return_dict[el.tag] = None
            children = el.getchildren()
            if children:
                return_dict[el.tag] = self._xml_to_dict(children)
            else:
                return_dict[el.tag] = el.text
        return return_dict



    def _update_capabilities(self):
        res = self._make_ocs_request(
                'GET',
                self.OCS_SERVICE_CLOUD,
                'capabilities'
                )
        if res.status_code == 200:
            tree = ET.fromstring(res.content)
            self._check_ocs_status(tree)

            data_el = tree.find('data')
            apps = {}
            for app_el in data_el.find('capabilities'):
                app_caps = {}
                for cap_el in app_el:
                    app_caps[cap_el.tag] = cap_el.text
                apps[app_el.tag] = app_caps

            self._capabilities = apps

            version_el = data_el.find('version/string')
            edition_el = data_el.find('version/edition')
            self._version = version_el.text
            if edition_el.text is not None:
                self._version += '-' + edition_el.text


            return self._capabilities
        raise HTTPResponseError(res)

















class MeinDialog(QtWidgets.QDialog):
    def __init__(self):
        QtWidgets.QDialog.__init__(self)
        scriptdir=os.path.dirname(os.path.abspath(__file__))
        uifile=os.path.join(scriptdir,'nextcloudusers.ui')
        winicon=os.path.join(scriptdir,'appicon.png')
        
        self.ui = uic.loadUi(uifile)        # load UI
        self.ui.setWindowIcon(QIcon(winicon))
        self.ui.exit.clicked.connect(self.onAbbrechen)        # setup Slots
        self.ui.start.clicked.connect(self.testLogindata)
        self.ui.pickfile.clicked.connect(self.selectFile)

        self.extraThread = QtCore.QThread()
        self.worker = Worker(self)
        self.worker.moveToThread(self.extraThread)
        self.extraThread.started.connect(lambda: self.worker.createAccounts(self.ocinstance,
                                                                            self.group,
                                                                            self.users) )
        self.extraThread.finished.connect(lambda: self.finished(self.createdusercount))
        self.worker.processed.connect(self.updateProgress)
        self.worker.finished.connect(self.finished)

        ###########    delete loginDATA  !!!!!     #######
        self.homepage_url = ""
        self.admin_username = ""
        self.admin_password = ""
        self.group = "students"
        self.users = ""
        self.usercount = 0
        self.createdusercount = 0
        self.ocinstance = ""
 
    def updateProgress(self, line):
        self.ui.errorlabel.setText("<b>%s</b>" %line)
        self.tolog(line) # print everything to a log!!

    def tolog(self, line):
        print ("-------------\n%s\n" %line)
        self.ui.processlog.append(line)



    def selectFile(self):
        """
        parses a comma separated textfile csv for usernames and passwords
        replaces all specialcharacters in usernames
        populates self.users
        """
        filedialog = QtWidgets.QFileDialog()
        filedialog.setDirectory(USER_HOME_DIR)  # set default directory
        file_patharray = filedialog.getOpenFileName()  # get filename
        file_path = file_patharray[0]
        filename = file_path.rsplit('/', 1)
        count = 1
        users = []
        try:
            file_lines = open(file_path, 'r').readlines()
        except IOError:
            print ("no file selected")
            return
        
        if file_lines != "":
            for line in file_lines:
                if line == "\n":
                    continue
                fields = [final.strip() for final in line.split(',')]
                if not len(fields) in [3]:
                    self.updateProgress("%d fields: %s" %(len(fields), fields))
                    self.updateProgress("Line %d has less or more than 3 fields. Skip." % count)
                    count += 1
                    continue
                users.append(fields)
             
        self.usercount = len(users)
        self.users = users
        
        self.tolog("Usernames:\n")
        userchanged = False
        changecount = 0
        for user in self.users:  ## replace specialcharacters in usernames ! äöüßé
            user[0] = user[0].lower().replace(" ", "")
            user[1] = user[1].lower().replace(" ", "")
     
            chars = set('âáàäèéêěëìíǐîïòǒóôõöùǔúûüćĉčß')
            if any((c in chars) for c in user[0]) or any((c in chars) for c in user[1]):
                
                user[0] = re.sub("[âáàä]", "a", user[0])
                user[0] = re.sub("[èéêěë]", "e", user[0])
                user[0] = re.sub("[ìíǐîï]", "i", user[0])
                user[0] = re.sub("[òǒóôõö]", "o", user[0])
                user[0] = re.sub("[ùǔúûü]", "u", user[0])
                user[0] = re.sub("[ćĉč]", "c", user[0])
                user[0] = re.sub("[ß]", "s", user[0])
               
                user[1] = re.sub("[âáàä]", "a", user[1])
                user[1] = re.sub("[èéêěë]", "e", user[1])
                user[1] = re.sub("[ìíǐîï]", "i", user[1])
                user[1] = re.sub("[òǒóôõö]", "o", user[1])
                user[1] = re.sub("[ùǔúûü]", "u", user[1])
                user[1] = re.sub("[ćĉč]", "c", user[1])
                user[1] = re.sub("[ß]", "s", user[1])
               
                changecount += 1
            
            self.tolog(">>  %s.%s   [%s]" % (user[0], user[1], user[2]))

        self.updateProgress("Found %d usernames and replaced specialcharacters in %s. (Check Log !)" % (self.usercount, changecount))
        self.ui.filename.setText("'%s'  |  %s Benutzer gefunden" %(filename[1],len(users)))
        return





    def testLogindata(self):
        """ fetches user information from UI
            tries to log in and checks if group exists
            starts user creation process if everything is ok
        """
        #FIXME   check if everything is set up correctly.. no empty strings !!!!!
        self.homepage_url = self.ui.domain.text().strip('\n')
        self.admin_username = self.ui.admin.text()
        self.admin_password = self.ui.password.text()
        self.group = self.ui.group.text()
        
        if self.users == "":
            self.updateProgress("Please add some users first")
            return
        
        if self.users == "" or self.homepage_url == "" or self.admin_username == "" or self.admin_password == "" or self.group == "":
            self.updateProgress("Please fill out all connection parameters") 
            self.enabledUI(True)
            return
        
        self.updateProgress("Trying to log in")
    
        self.ocinstance = Client(self.homepage_url)
        self.ocinstance.login(self.admin_username, self.admin_password)

        try:   #test connection info 
            adminexists = self.ocinstance.user_exists(self.admin_username)
        except:
            self.ocinstance._session.close()
            self.ocinstance._session = None
            self.updateProgress("Please double check your connection parameters") 
            self.enabledUI(True)
            return
        
        if not self.ocinstance.group_exists(self.group): #check if group exists
            self.updateProgress("The group %s does not exist" %self.group) 
            self.enabledUI(True)
            return   
        
        self.updateProgress("Login Data OK !") 
    
    
    
        # start user creation process
        self.enabledUI(False)
        self.extraThread.start()

    
    def onAbbrechen(self):    # Exit button
        self.ui.close()
        os._exit(0)

    def finished(self, createdusers=0):
        self.createdusercount = createdusers
        self.updateProgress("%s out of %s User Accounts created !" %(createdusers, self.usercount) )
        self.extraThread.quit() #extraThread must be killed here otherwise its blocking a second try
        self.extraThread.wait()
        self.enabledUI(True)

    def enabledUI(self, boolean):
        """toggles ui buttons"""
        self.ui.start.setEnabled(boolean)
        self.ui.pickfile.setEnabled(boolean)
        self.ui.domain.setEnabled(boolean)
        self.ui.admin.setEnabled(boolean)
        self.ui.password.setEnabled(boolean)
        self.ui.group.setEnabled(boolean)
   























class  Worker(QtCore.QObject):
    def __init__(self, meindialog):
        super(Worker, self).__init__()
        self.meindialog = meindialog

    processed = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(int)


    def createAccounts(self, ocinstance, group, users):   
        """ Shows a confirmation dialog and 
        creates all user accounts
        
        :param ocinstance: instance of the owncloud/nextcloud client
        :param group: name of the group user is to be addded
        :param users: list of lists [name, surname, password]
        
        """
        userlist = []
        for user in users:
            username = "%s.%s" %(user[0],user[1])
            userlist.append(username)
        
        userstring = ""
        for user in userlist:
            userstring += "\n"+user
    
        #self.processed.emit("This will create the following users: \n\n%s " % (userlist)) 
        
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Information)
        msg.setText("Nextcloud Users")
        msg.setInformativeText("Do you want to create <b>%s</b> users now ?"  %len(users))
        msg.setWindowTitle("Adding Nextcloud Useraccounts")
        msg.setDetailedText("This will create the following users: \n%s " % (userstring))
        msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        retval = msg.exec_()   # 16384 = yes, 65536 = no
       
       
        # CREATE USERACCOUNTS NOW !!
        createdusers = 0
        if str(retval) == "16384":
            for user in users:
                username = "%s.%s" %(user[0],user[1])
                password = user[2]
                
                if ocinstance.user_exists(username):    #check if user exists
                    self.processed.emit("<b>ERROR</b> The username '%s' is already taken!" %username) 
                else:
                    usercreated = False
                    try:
                        usercreated = ocinstance.create_user(username,password)         # OCS error: 106 login user has no right to create this account (group admins cant create users without groups)
                    except Exception as e: 
                        if "101" in str(e): 
                            errormsg = "invalid input data"
                        elif "102" in str(e):
                            errormsg = "username already exists"
                        elif "103" in str(e):
                            errormsg = "unknown error occurred whilst adding the user"
                        else: 
                            errormsg = ""
                            
                        self.processed.emit("<b>ERROR</b> Username '%s' raised: %s | %s" %(username, e, errormsg) )
                        continue
                    
                    if usercreated:
                        createdusers+=1
                        self.processed.emit("User '%s' account creation success: %s" %(username, usercreated) )
                        ocinstance.add_user_to_group(username,group)
        else:
            ocinstance._session.close()    
            ocinstance._session = None
                    
        self.finished.emit(createdusers)   




app = QtWidgets.QApplication(sys.argv)
dialog = MeinDialog()
dialog.ui.show()   #show user interface
sys.exit(app.exec_())

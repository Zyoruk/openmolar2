#! /usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
##                                                                           ##
##  Copyright 2010, Neil Wallace <rowinggolfer@googlemail.com>               ##
##                                                                           ##
##  This program is free software: you can redistribute it and/or modify     ##
##  it under the terms of the GNU General Public License as published by     ##
##  the Free Software Foundation, either version 3 of the License, or        ##
##  (at your option) any later version.                                      ##
##                                                                           ##
##  This program is distributed in the hope that it will be useful,          ##
##  but WITHOUT ANY WARRANTY; without even the implied warranty of           ##
##  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the            ##
##  GNU General Public License for more details.                             ##
##                                                                           ##
##  You should have received a copy of the GNU General Public License        ##
##  along with this program.  If not, see <http://www.gnu.org/licenses/>.    ##
##                                                                           ##
###############################################################################

import re
import sys
from xmlrpclib import Fault as ServerFault
from PyQt4 import QtGui, QtCore

from lib_openmolar.common.connect import ProxyClient

from lib_openmolar.common.datatypes import ConnectionData
from lib_openmolar.common.qt4.widgets import RestorableApplication

from lib_openmolar.admin import qrc_resources

from lib_openmolar.admin.connect import AdminConnection

from lib_openmolar.admin.db_tools.proxy_manager import ProxyManager

from lib_openmolar.common.qt4.dialogs import *
from lib_openmolar.admin.qt4.dialogs import *

from lib_openmolar.admin.qt4.classes import (
    AdminTabWidget,
    LogWidget,
    AdminSessionWidget)

from lib_openmolar.common.qt4.postgres.postgres_mainwindow import \
    PostgresMainWindow


class AdminMainWindow(PostgresMainWindow, ProxyManager):
    '''
    This class is the core application.
    '''
    log = LOGGER

    CONN_CLASS = AdminConnection

    def __init__(self, parent=None):
        PostgresMainWindow.__init__(self, parent)
        self.setMinimumSize(600, 400)

        self.setWindowTitle("Openmolar Admin")
        self.setWindowIcon(QtGui.QIcon(":icons/openmolar-server.png"))

        ## Main Menu

        ## "file"

        icon = QtGui.QIcon.fromTheme("network-wired")
        self.action_omconnect = QtGui.QAction(icon,
            "OM %s"% _("Connect"), self)
        self.action_omconnect.setToolTip(
                                _("Connect (to an openmolar server)"))

        icon = QtGui.QIcon.fromTheme("network-error")
        self.action_omdisconnect = QtGui.QAction(icon,
            "OM %s"% _("Disconnect"), self)
        self.action_omdisconnect.setToolTip(
            _("Disconnect (from an openmolar server)"))

        insertpoint = self.action_connect
        self.menu_file.insertAction(insertpoint, self.action_omconnect)
        self.menu_file.insertAction(insertpoint,self.action_omdisconnect)
        self.menu_file.insertSeparator(insertpoint)

        insertpoint = self.action_connect
        self.main_toolbar.insertAction(insertpoint, self.action_omconnect)
        self.main_toolbar.insertAction(insertpoint, self.action_omdisconnect)
        self.main_toolbar.insertSeparator(insertpoint)

        ## "Database Tools"

        self.menu_database = QtGui.QMenu(_("&Database Tools"), self)
        self.insertMenu_(self.menu_database)

        icon = QtGui.QIcon.fromTheme("contact-new")
        self.action_new_database = QtGui.QAction(icon,
            _("New Openmolar Database"), self)

        self.action_populate_demo = QtGui.QAction(icon,
            _("Populate database with demo data"), self)

        self.menu_database.addAction(self.action_new_database)
        self.menu_database.addAction(self.action_populate_demo)

        tb_database = QtGui.QToolButton(self)
        icon = QtGui.QIcon(":icons/database.png")
        tb_database.setIcon(icon)
        tb_database.setText(_("Database Tools"))
        tb_database.setToolTip(_("A variety of database tools"))
        tb_database.setPopupMode(tb_database.InstantPopup)
        tb_database.setMenu(self.menu_database)

        self.insertToolBarWidget(tb_database, True)

        self.log_widget = LogWidget(LOGGER, self.parent())
        self.log_widget.welcome()
        self.log_dock_widget = QtGui.QDockWidget(_("Log"), self)
        self.log_dock_widget.setObjectName("LogWidget") #for save state!
        self.log_dock_widget.setWidget(self.log_widget)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea,
            self.log_dock_widget)

        self.action_show_log = self.log_dock_widget.toggleViewAction()
        insertpoint = self.action_show_statusbar
        self.menu_view.insertAction(insertpoint, self.action_show_log)

        #take a note of this before restoring settings
        self.system_font = self.font()

        ####       now load stored settings                                ####
        self.loadSettings()
        tb_database.setToolButtonStyle(self.main_toolbar.toolButtonStyle())

        self.pg_sessions = []

        self.end_pg_sessions()
        self.connect_signals()
        self.show()

        QtCore.QTimer.singleShot(100, self.setBriefMessageLocation)
        QtCore.QTimer.singleShot(100, self._init_proxies)

    def connect_signals(self):
        '''
        set up signals/slots
        '''

        ##some old style connects are used to ensure argument (bool=0)
        ##is not passed to the slot

        self.action_omconnect.triggered.connect(self.om_connect)
        self.action_omdisconnect.triggered.connect(self.om_disconnect)

        self.action_show_log.triggered.connect(self.show_log)

        self.action_new_database.triggered.connect(self.create_new_database)
        self.action_populate_demo.triggered.connect(self.populate_demo)

        self.connect(self.central_widget, QtCore.SIGNAL("end_pg_sessions"),
            self.end_pg_sessions)

        self.known_server_widget.shortcut_clicked.connect(self.manage_shortcut)
        self.known_server_widget.server_changed.connect(self.set_proxy_index)

    @property
    def central_widget(self):
        '''
        overwrite the property of the Base Class
        '''
        if self._central_widget is None:
            LOGGER.debug("AdminMainWindow.. creating central widget")
            self._central_widget = AdminTabWidget(self)
            self.known_server_widget = self._central_widget.known_server_widget

            self._central_widget.add = self._central_widget.addTab
            self._central_widget.remove = self._central_widget.removeTab

        return self._central_widget

    @property
    def new_session_widget(self):
        '''
        overwrite the property of the Base Class
        '''
        admin_session_widget = AdminSessionWidget(self)

        return admin_session_widget

    def _init_proxies(self):
        '''
        called at startup, and by the om_connect action
        '''
        ProxyManager._init_proxies(self)
        self.known_server_widget.clear()
        for client in self.proxy_clients:
            self.known_server_widget.add_proxy_client(client)
        self.known_server_widget.setEnabled(True)

    def om_disconnect(self):
        ProxyManager.om_disconnect(self)
        self.known_server_widget.clear()
        self.known_server_widget.setEnabled(False)

    def switch_server_user(self):
        self.advise("we need to up your permissions for this",1)
        return False

    def show_log(self):
        '''
        toggle the state of the log dock window
        '''
        if self.action_show_log.isChecked():
            self.log_dock_widget.show()
        else:
            self.log_dock_widget.hide()

    def end_pg_sessions(self, shutting_down=False):
        '''
        overwrite baseclass function
        '''
        if shutting_down or (
        self.has_pg_connection and self.central_widget.closeAll()):
            PostgresMainWindow.end_pg_sessions(self)
        else:
            if self.central_widget.closeAll():
                PostgresMainWindow.end_pg_sessions(self)
        self.update_session_status()

    def use_proxy_database(self, db_name):
        '''
        user has clicked on a link provided by a :doc:`ProxyClient`
        requesting a session on dbname
        '''
        ## TODO this should use more information pulled from the proxy server

        result, user, passwd = self.get_user_pass(db_name)
        if not result:
            return

        client = self.known_server_widget.current_client
        host = client.host
        port = 5432
        connection_data = ConnectionData(
            connection_name = "%s_%s:%s"% (db_name, host, 5432),
            host = host,
            user = user,
            password = passwd,
            port = 5432,
            db_name = db_name)

        pg_session = AdminConnection(connection_data)
        if self._attempt_connection(pg_session):
            self.add_session(pg_session)
        self.update_session_status()

    def create_new_database(self):
        '''
        raise a dialog, then create a database with the chosen name
        '''
        dl = NewDatabaseDialog(self)
        if not dl.exec_() or dl.database_name == "":
            self.display_proxy_message()
            return
        dbname = dl.database_name
        ProxyManager.create_database(self, dbname)

    def create_demo_database(self):
        '''
        initiates the demo database
        '''
        LOGGER.info("creating demo database")
        result = ProxyManager.create_demo_database(self)
        LOGGER.info(result)
        if (result and
        QtGui.QMessageBox.question(self, _("Confirm"),
        u"%s"% _("Populate with demo data now?"),
        QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel,
        QtGui.QMessageBox.Ok) == QtGui.QMessageBox.Ok):
            self.populate_demo()

        self.display_proxy_message()

    def set_permissions(self, database):
        '''
        alters permissions on a known database
        '''
        dl = NewUserPasswordDialog(self)
        result, user, password = dl.getValues()
        message = "TODO - enable set_permissions for %s, %s"% (user, "****")
        self.advise(message, 1)
        if result:
            LOGGER.info(message)

    def populate_demo(self):
        '''
        catches signal when user hits the demo action
        '''
        if self.session_widgets == []:
            self.advise("no session started",1)
            return

        if len(self.session_widgets) == 1:
            i = 0
        else:
            i = self.central_widget.currentIndex()-1

        conn = self.session_widgets[i].pg_session
        LOGGER.info("calling populate demo on session %s"% conn)
        dl = PopulateDemoDialog(conn, self)
        if not dl.exec_():
            self.advise("Demo data population was abandoned", 1)

    def manage_db(self, dbname):
        '''
        raise a dialog, and provide database management tools
        '''
        dl = ManageDatabaseDialog(dbname, self)
        if dl.exec_():
            if dl.manage_users:
                self.advise("manage users")
            elif dl.drop_db:
                self.advise(u"%s %s"%(_("dropping database"), dbname))
                self.drop_db(dbname)

    def closeEvent(self, event=None):
        '''
        re-implement the close event of QtGui.QMainWindow, and check the user
        really meant to do this.
        '''
        if (self.log_widget.dirty and
        QtGui.QMessageBox.question(self, _("Confirm"),
        _("You have unsaved log changes - Quit Application?"),
        QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
        QtGui.QMessageBox.Yes) == QtGui.QMessageBox.No):
            event.ignore()
        else:
            self.saveSettings()
            self.end_pg_sessions(shutting_down=True)

    @property
    def confirmDataOverwrite(self):
        '''
        check that the user is prepared to lose any changes
        '''
        result = QtGui.QMessageBox.question(self, _("confirm"),
        "<p>%s<br />%s</p>"% (
        _("this action will overwrite any current data stored"),
        _("proceed?")),
        QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel,
        QtGui.QMessageBox.Ok )
        return result == QtGui.QMessageBox.Ok

    def save_template(self):
        '''
        save the template, so it can be re-used in future
        '''
        try:
            filepath = QtGui.QFileDialog.getSaveFileName(self,
            _("save template file"),"",
            _("openmolar template files ")+"(*.om_xml)")
            if filepath != '':
                if not re.match(".*\.om_xml$", filepath):
                    filepath += ".om_xml"
                f = open(filepath, "w")
                f.write(self.template.toxml())
                f.close()
                self.advise(_("Template Saved"), 1)
            else:
                self.advise(_("operation cancelled"), 1)
        except Exception, e:
            self.advise(_("Template not saved")+" - %s"% e, 2)

    def load_template(self):
        '''
        change the default template for a new database
        '''
        if not self.confirmDataOverwrite:
            return
        filename = QtGui.QFileDialog.getOpenFileName(self,
        _("load an existing template file"),"",
        _("openmolar template files")+" (*.om_xml)")

        if filename != '':
            try:
                self.template = minidom.parse(str(filename))
                self.advise(_("template loaded sucessfully"),1)
            except Exception, e:
                self.advise(_("error parsing template file")+" - %s"% e, 2)
        else:
            self.advise(_("operation cancelled"), 1)

    def loadSettings(self):
        PostgresMainWindow.loadSettings(self)
        qsettings = QtCore.QSettings()

        qsettings.setValue("connection_conf_dir",
            "/etc/openmolar/admin/connections")

    def saveSettings(self):
        PostgresMainWindow.saveSettings(self)

    def show_about(self):
        '''
        raise a dialog showing version info etc.
        '''
        ABOUT_TEXT = "<p>%s</p><pre>%s\n%s</pre><p>%s<br />%s</p>"% ( _('''
This application provides tools to manage and configure your database server
and can set up either a demo openmolar database, or a
customised database for a specific dental practice situation.'''),
_("Version"), AD_SETTINGS.VERSION,
"<a href='http://www.openmolar.com'>www.openmolar.com</a>",
'Neil Wallace - rowinggolfer@googlemail.com')
        self.advise(ABOUT_TEXT, 1)

    def show_help(self):
        '''
        todo - this is the same as show_about
        '''
        self.show_about()

    def switch_server_user(self):
        '''
        to change the user of the proxy up to admin
        overwrites :doc:`ProxyManager` function
        '''
        LOGGER.debug("switch_server_user called")
        self.advise("we need to up your permissions for this", 1)
        dl = UserPasswordDialog(self)
        dl.set_name("admin")
        if dl.exec_():
            name = dl.name
            psword = dl.password
            self.advise("NOW WHAT", 2)
            #AD_SETTINGS.proxy_user = ProxyUser(name, psword)
            #force reload of server at next use
            self._proxy_server = None
            return True
        return False

    def manage_shortcut(self, url):
        '''
        the admin browser
        (which commonly contains messages from the openmolar_server)
        is connected to this slot.
        when a url is clicked it finds it's way here for management.
        unrecognised signals are send to the user via the notification.
        '''
        LOGGER.debug("manage_shortcut %s"% url)
        try:
            if url == "install_demo":
                LOGGER.debug("Install demo called via shortcut")
                self.create_demo_database()
            elif re.match("connect_.*", url):
                dbname = re.match("connect_(.*)", url).groups()[0]
                self.advise("start session on database %s"% dbname)
                self.use_proxy_database(dbname)
            elif re.match("manage_.*", url):
                dbname = re.match("manage_(.*)", url).groups()[0]
                self.manage_db(dbname)
            else:
                self.advise("%s<hr />%s"% (_("Shortcut not found"), url), 2)
        except ProxyManager.PermissionError as exc:
            self.advise("%s<hr />%s" %(_("Permission denied"), exc), 2)

def main():

    app = RestorableApplication("openmolar-admin")
    ui = AdminMainWindow()
    ui.show()
    app.exec_()
    app = None

if __name__ == "__main__":
    import gettext
    gettext.install("openmolar")
    sys.exit(main())

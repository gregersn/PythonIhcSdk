"""
Wraps the ihcclient in a more user friendly interface to handle lost connection
Notify thread to handle change notifications
"""
# pylint: disable=invalid-name, bare-except, too-many-instance-attributes
import threading
import time
from ihcsdk.ihcclient import IHCSoapClient, IHCSTATE_READY

class IHCController:
    """
    Implements the notification thread and
    will re-authenticate if needed.
    """
    _mutex = threading.Lock()

    def __init__(self, url: str, username: str, password: str):
        self.client = IHCSoapClient(url)
        self._username = username
        self._password = password
        self._ihcevents = {}
        self._notifythread = threading.Thread(target=self._notify_fn)
        self._notifyrunning = False
        self._newnotifyids = []
        self._project = None

    def authenticate(self) -> bool:
        """Authenticate and enable the registered notifications"""
        with IHCController._mutex:
            if not self.client.authenticate(self._username, self._password):
                return False
            if self._ihcevents:
                self.client.enable_runtime_notifications(self._ihcevents.keys())
            return True

    def disconnect(self):
        """Disconnect by stopping the notification thread
        TODO call disconnect on ihcclient
        """
        self._notifyrunning = False

    def get_runtime_value(self, ihcid: int):
        """ Get runtime value with re-authenticate if needed"""
        try:
            return self.client.get_runtime_value(ihcid)
        except:
            self.re_authenticate()
            return self.client.get_runtime_value(ihcid)

    def set_runtime_value_bool(self, ihcid: int, value: bool) -> bool:
        """ Set bool runtime value with re-authenticate if needed"""
        try:
            return self.client.set_runtime_value_bool(ihcid, value)
        except:
            self.re_authenticate()
            return self.client.set_runtime_value_bool(ihcid, value)

    def set_runtime_value_int(self, ihcid: int, value: int) -> bool:
        """ Set integer runtime value with re-authenticate if needed"""
        try:
            return self.client.set_runtime_value_int(ihcid, value)
        except:
            self.re_authenticate()
            return self.client.set_runtime_value_int(ihcid, value)

    def set_runtime_value_float(self, ihcid: int, value: float) -> bool:
        """ Set float runtime value with re-authenticate if needed"""
        try:
            return self.client.set_runtime_value_float(ihcid, value)
        except:
            self.re_authenticate()
            return self.client.set_runtime_value_float(ihcid, value)

    def get_project(self) -> str:
        """ Get the ihc project and make sure controller is ready before"""
        with IHCController._mutex:
            if self._project is None:
                if self.client.get_state() != IHCSTATE_READY:
                    if self.client.wait_for_state_change(IHCSTATE_READY, 10) != IHCSTATE_READY:
                        return None
                self._project = self.client.get_project()
        return self._project

    def add_notify_event(self, resourceid: int, callback, delayed=False):
        """ Add a notify callback for a specified resource id
        If delayed is set to true the enable request will be send from the
        notofication thread
        """
        with IHCController._mutex:
            if resourceid in self._ihcevents:
                self._ihcevents[resourceid].append(callback)
            else:
                self._ihcevents[resourceid] = [callback]
                if delayed:
                    self._newnotifyids.append(resourceid)
                else:
                    if not self.client.enable_runtime_notification(resourceid):
                        return False
            if not self._notifyrunning:
                self._notifythread.start()

            return True

    def _notify_fn(self):
        """The notify thread function."""
        self._notifyrunning = True
        while self._notifyrunning:
            try:
                with IHCController._mutex:
                    # Are there are any new ids to be added?
                    if self._newnotifyids:
                        self.client.enable_runtime_notifications(self._newnotifyids)
                        self._newnotifyids = []

                changes = self.client.wait_for_resource_value_changes()
                if changes is False:
                    self.re_authenticate()
                    continue
                for ihcid in changes:
                    value = changes[ihcid]
                    if ihcid in self._ihcevents:
                        for callback in self._ihcevents[ihcid]:
                            callback(ihcid, value)
            except:
                self.re_authenticate()

    def re_authenticate(self):
        """Authenticate again after failure.
           Keep trying with 10 sec interval"""
        while not self.authenticate():
            #wait 10 seconds before we try to authenticate again
            time.sleep(10)
            if not self._notifyrunning:
                break

'''
Created on 2015/11/9

:author: hubo
'''
from vlcp.config import defaultconfig
from vlcp.server.module import Module, api
from vlcp.event.core import TimerEvent
from vlcp.event.runnable import RoutineContainer
from time import time
import functools

@defaultconfig
class Knowledge(Module):
    '''
    Simple KV-cache in memory. A base for other KV-DB.
    Data is automatically removed after timeout.
    Use knowledge instead of local storage in modules so data is not lost on module restarting.
    '''
    _default_checkinterval = 300
    service = True
    def __init__(self, server):
        '''
        Constructor
        '''
        Module.__init__(self, server)
        self.timeoutroutine = RoutineContainer(self.scheduler)
        self.timeoutroutine.main = self._timeout
        self.db = {}
        self.routines.append(self.timeoutroutine)
        self.createAPI(api(self.get),
                       api(self.set),
                       api(self.delete),
                       api(self.mget),
                       api(self.mset),
                       api(self.update),
                       api(self.mupdate))
    def _timeout(self):
        th = self.scheduler.setTimer(self.checkinterval, self.checkinterval)
        try:
            tm = TimerEvent.createMatcher(th)
            while True:
                yield (tm,)
                t = time()
                timeouts = [k for k,v in self.db.items() if v[1] is not None and v[1] < t]
                for k in timeouts:
                    del self.db[k]
        finally:
            self.scheduler.cancelTimer(th)
    def _get(self, key, currtime):
        v = self.db.get(key)
        if v is not None:
            if v[1] is not None and v[1] < currtime:
                del self.db[key]
                return None
        return v
    def _set(self, key, value, currtime, timeout):
        if timeout is not None and timeout <= 0:
            try:
                del self.db[key]
            except KeyError:
                pass
        else:
            self.db[key] = (value, currtime + timeout)
    def get(self, key, timeout = None):
        "Get value from key"
        t = time()
        v = self._get(key, t)
        if v is None:
            return None
        if timeout is not None:
            self._set(key, v[0], t, timeout)
        return v[0]
    def set(self, key, value, timeout = None):
        "Set value to key, with an optional timeout"
        self._set(key, value, time(), timeout)
        return None
    def delete(self, key):
        try:
            del self.db[key]
        except KeyError:
            pass
        return None
    def mget(self, keys):
        "Get multiple values from multiple keys"
        t = time()
        return [self._get(k, t)[0] for k in keys]
    def mset(self, kvpairs, timeout = None):
        "Set multiple values on multiple keys"
        d = kvpairs
        if hasattr(d, 'items'):
            d = d.items()
        if timeout is not None and timeout <= 0:
            for k,_ in d:
                self.delete(k)
        else:
            t = time() + timeout
            self.db.update(((k, (v, t)) for k,v in d))
            return None
    def update(self, key, updater, timeout = None):
        '''
        Update in-place with a custom function
        
        :param key: key to update
        
        :param updater: func(k,v), should return a new value to update, or return None to delete
        
        :param timeout: new timeout
        
        :returns: the updated value, or None if deleted
        '''
        return self._update(key, updater, time(), timeout)
    def _update(self, key, updater, currtime, timeout):
        v = self._get(key, currtime)
        if v is not None:
            v = v[0]
        newv = updater(key, v)
        if newv is not None:
            self._set(key, newv, currtime, timeout)
        else:
            self.delete(key)
        return newv
    def mupdate(self, keys, updater, timeout = None):
        "Update multiple keys in-place with a custom function, see update"
        t = time()
        for k in keys:
            self._update(k, updater, t, timeout)

def return_self_updater(func):
    '''
    Run func, but still return v. Useful for using knowledge.update with operates like append, extend, etc.
    e.g. return_self(lambda k,v: v.append('newobj'))
    '''
    @functools.wraps(func)
    def decorator(k,v):
        func(k,v)
        return v
    return decorator

def escape_key(k):
    "Escape k, ensuring there is not a '.' in the string."
    return k.replace('+','+_').replace('.','++')

def unescape_key(k):
    "Unescape key to get '.' back"
    return k.replace('++', '.').replace('+_','+')

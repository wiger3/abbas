import copy
import json

class AbbasConfig:
    def __init__(self, path: str):
        self._path = path
        self.reload()
    
    def reload(self):
        with open(self._path, 'r', encoding='utf-8') as file:
            self._data = json.load(file)
        print("Loaded config:")
        print(self)
    
    def __getattribute__(self, name: str):
        if name[0] == '_' or name == 'reload':
            return object.__getattribute__(self, name)
        return self._data[name] if name in self._data else None
    
    def __repr__(self) -> str:
        data = copy.deepcopy(self._data)
        if 'mysql' in data and 'password' in data['mysql']:
            data['mysql']['password'] = '***'
        return repr(data)
    def __str__(self) -> str:
        data = copy.deepcopy(self._data)
        if 'mysql' in data and 'password' in data['mysql']:
            data['mysql']['password'] = '***'
        return str(data)

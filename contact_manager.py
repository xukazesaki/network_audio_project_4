import json
import os

class ContactManager:
    def __init__(self, filename="contacts.json"):
        self.filename = filename
        self.contacts = self.load()

    def load(self):
        if not os.path.exists(self.filename):
            return {}
        with open(self.filename, "r") as f:
            return json.load(f)

    def save(self):
        with open(self.filename, "w") as f:
            json.dump(self.contacts, f, indent=4)

    def add(self, name, addr):
        self.contacts[name] = addr
        self.save()

    def delete(self, name):
        if name in self.contacts:
            del self.contacts[name]
            self.save()

    def get(self, name):
        return self.contacts.get(name)

    def get_all(self):
        return self.contacts
    
print("ContactManager loaded")
import json
import os

from src.core.config import CONTACTS_FILE


class ContactManager:
    # 初始化联系人存储，并加载已有联系人数据。
    def __init__(self, filename: str = CONTACTS_FILE):
        self.filename = filename
        self.contacts = self.load()

    # 从磁盘读取联系人；读取失败时返回空字典。
    def load(self):
        if not os.path.exists(self.filename):
            return {}
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    # 将当前联系人数据保存到磁盘。
    def save(self):
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.contacts, f, ensure_ascii=False, indent=2)

    # 新增联系人，或更新已有联系人的备注。
    def add(self, name: str, remark: str):
        self.contacts[name] = remark
        self.save()

    # 删除一个已保存的联系人。
    def delete(self, name: str):
        if name in self.contacts:
            del self.contacts[name]
            self.save()

    # 获取单个联系人的备注，不存在时返回默认值。
    def get(self, name: str, default=None):
        return self.contacts.get(name, default)

    # 返回联系人数据的浅拷贝，供界面安全读取。
    def get_all(self):
        return dict(self.contacts)

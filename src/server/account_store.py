import json
from copy import deepcopy
from datetime import datetime

from src.core.config import SERVER_ACCOUNTS_FILE


class AccountStore:
    # 服务端账户与好友电话本数据的本地存储层。
    def __init__(self, file_path=SERVER_ACCOUNTS_FILE):
        self.file_path = file_path
        self.data = self._load()

    # 返回一个空的账户数据结构，供首次启动或异常恢复时使用。
    def _empty_store(self):
        return {"users": {}}

    # 生成统一的 UTC 时间戳，便于记录账户创建和更新时间。
    def _now(self):
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"

    # 从磁盘加载账户数据；文件缺失或格式异常时回退为空结构。
    def _load(self):
        if not self.file_path.exists():
            return self._empty_store()

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return self._empty_store()

        if not isinstance(data, dict):
            return self._empty_store()

        data.setdefault("users", {})
        return data

    # 将当前账户数据写回服务端 data 目录。
    def save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # 判断某个用户名是否已经注册。
    def has_user(self, username):
        return username in self.data["users"]

    # 获取单个用户的完整信息，并返回副本避免外部直接修改内存数据。
    def get_user(self, username):
        user = self.data["users"].get(username)
        return deepcopy(user) if user else None

    # 返回当前所有已注册用户名列表。
    def list_users(self):
        return sorted(self.data["users"].keys())

    # 创建新用户，并为好友关系与申请列表初始化默认字段。
    def create_user(self, username, nickname=""):
        if self.has_user(username):
            return False

        self.data["users"][username] = {
            "username": username,
            "nickname": nickname or username,
            "friends": [],
            "pending_incoming": [],
            "pending_outgoing": [],
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self.save()
        return True

    # 更新用户资料，目前仅保留昵称字段。
    def update_profile(self, username, **fields):
        user = self.data["users"].get(username)
        if not user:
            return False

        if "nickname" in fields and fields["nickname"] is not None:
            user["nickname"] = fields["nickname"]

        user["updated_at"] = self._now()
        self.save()
        return True

    # 获取指定用户的好友列表。
    def list_friends(self, username):
        user = self.data["users"].get(username)
        if not user:
            return []
        return sorted(user.get("friends", []))

    # 获取指定用户收到但尚未处理的好友申请列表。
    def list_pending_incoming(self, username):
        user = self.data["users"].get(username)
        if not user:
            return []
        return sorted(user.get("pending_incoming", []))

    # 获取指定用户已经发出但尚未处理的好友申请列表。
    def list_pending_outgoing(self, username):
        user = self.data["users"].get(username)
        if not user:
            return []
        return sorted(user.get("pending_outgoing", []))

    # 发起好友申请，并同时更新发送方与接收方的申请状态。
    def add_friend_request(self, sender, target):
        if sender == target:
            return False, "cannot_add_self"
        if not self.has_user(sender) or not self.has_user(target):
            return False, "user_not_found"

        sender_user = self.data["users"][sender]
        target_user = self.data["users"][target]

        if target in sender_user["friends"]:
            return False, "already_friends"
        if target in sender_user["pending_outgoing"]:
            return False, "request_already_sent"
        if sender in target_user["pending_outgoing"]:
            return False, "reverse_request_exists"

        if target not in sender_user["pending_outgoing"]:
            sender_user["pending_outgoing"].append(target)
        if sender not in target_user["pending_incoming"]:
            target_user["pending_incoming"].append(sender)

        sender_user["updated_at"] = self._now()
        target_user["updated_at"] = self._now()
        self.save()
        return True, "ok"

    # 同意好友申请，并将双方正式加入好友列表。
    def accept_friend_request(self, username, requester):
        if not self.has_user(username) or not self.has_user(requester):
            return False, "user_not_found"

        user = self.data["users"][username]
        requester_user = self.data["users"][requester]

        if requester not in user["pending_incoming"]:
            return False, "request_not_found"

        user["pending_incoming"].remove(requester)
        if username in requester_user["pending_outgoing"]:
            requester_user["pending_outgoing"].remove(username)

        # 如果双方曾经互相发起过申请，这里一并清理残留状态。
        if requester in user["pending_outgoing"]:
            user["pending_outgoing"].remove(requester)
        if username in requester_user["pending_incoming"]:
            requester_user["pending_incoming"].remove(username)

        if requester not in user["friends"]:
            user["friends"].append(requester)
        if username not in requester_user["friends"]:
            requester_user["friends"].append(username)

        user["updated_at"] = self._now()
        requester_user["updated_at"] = self._now()
        self.save()
        return True, "ok"

    # 拒绝好友申请，并清理双方的待处理状态。
    def reject_friend_request(self, username, requester):
        if not self.has_user(username) or not self.has_user(requester):
            return False, "user_not_found"

        user = self.data["users"][username]
        requester_user = self.data["users"][requester]

        if requester not in user["pending_incoming"]:
            return False, "request_not_found"

        user["pending_incoming"].remove(requester)
        if username in requester_user["pending_outgoing"]:
            requester_user["pending_outgoing"].remove(username)

        user["updated_at"] = self._now()
        requester_user["updated_at"] = self._now()
        self.save()
        return True, "ok"

    # 删除已有好友关系，并同步清理双方好友列表。
    def remove_friend(self, username, friend_name):
        if not self.has_user(username) or not self.has_user(friend_name):
            return False, "user_not_found"

        user = self.data["users"][username]
        friend_user = self.data["users"][friend_name]

        removed = False
        if friend_name in user["friends"]:
            user["friends"].remove(friend_name)
            removed = True
        if username in friend_user["friends"]:
            friend_user["friends"].remove(username)
            removed = True

        if not removed:
            return False, "friend_not_found"

        user["updated_at"] = self._now()
        friend_user["updated_at"] = self._now()
        self.save()
        return True, "ok"

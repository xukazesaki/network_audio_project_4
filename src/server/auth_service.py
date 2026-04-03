from src.server.account_store import AccountStore


class AuthService:
    # 轻量认证层：只基于用户名做注册与登录校验。

    def __init__(self, account_store=None):
        self.account_store = account_store or AccountStore()

    # 统一清理用户名输入，避免前后空格造成重复账户。
    def normalize_username(self, username):
        return (username or "").strip()

    # 校验用户名是否为空，并返回规范化后的结果。
    def validate_username(self, username):
        normalized = self.normalize_username(username)
        if not normalized:
            return False, "empty_username", normalized
        return True, "ok", normalized

    # 注册新用户；当前仅要求用户名唯一，不涉及密码。
    def register(self, username, nickname=""):
        ok, code, normalized = self.validate_username(username)
        if not ok:
            return False, code, None

        if self.account_store.has_user(normalized):
            return False, "username_taken", None

        created = self.account_store.create_user(normalized, nickname=nickname)
        if not created:
            return False, "username_taken", None

        return True, "ok", self.account_store.get_user(normalized)

    # 登录已有用户；当前仅检查账户是否存在。
    def login(self, username):
        ok, code, normalized = self.validate_username(username)
        if not ok:
            return False, code, None

        user = self.account_store.get_user(normalized)
        if not user:
            return False, "user_not_found", None

        return True, "ok", user

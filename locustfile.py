from locust import HttpUser, task, between
import random


class WebsiteUser(HttpUser):
    wait_time = between(1, 2)

    accounts = [
        ("admin", "adminpassword", "admin"),
        ("hongngoc", "ptit@123", "student"),
        ("stu1", "ptit@123", "student"),
        ("stu2", "ptit@123", "student"),
        ("gv_preview", "ptit@123", "lecturer"),
        ("ptit_preview", "ptit@123", "lecturer"),
        ("it_preview", "ptit@123", "lecturer"),
        ("hungnv", "ptit@123", "student"),
    ]

    def on_start(self):
        self.access_token = None
        self.login()

    def login(self):
        username, password, role = random.choice(self.accounts)

        # Gửi yêu cầu đăng nhập với dữ liệu dưới dạng form-urlencoded
        # và thêm header "Content-Type"
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = self.client.post("/token", {
            "username": username,
            "password": password
        }, name="/token", headers=headers)

        if response.status_code == 200:
            response_json = response.json()
            self.access_token = response_json.get("access_token")
            self.role = role
            print(f"✅ Đăng nhập thành công với vai trò: {self.role}")
        else:
            print(f"❌ Đăng nhập thất bại. Status code: {response.status_code}")
            print(f"Nội dung phản hồi: {response.text}")
            self.stop()

    @task
    def access_protected_page(self):
        if self.access_token:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            # Sử dụng API đã được bảo vệ như /users/me
            self.client.get("/users/me", headers=headers, name="Xem-thong-tin-user")
        else:
            self.login()
#!/usr/bin/env python3

import requests
import json
import sys
from datetime import datetime

class PromptManagerAPITester:
    def __init__(self, base_url="https://promptsrc.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_base = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.api_key = None

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
            self.failed_tests.append({"name": name, "details": details})

    def test_health_check(self):
        """Test health check endpoint"""
        try:
            response = requests.get(f"{self.api_base}/health", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                details += f", Response: {data}"
            self.log_test("Health Check", success, details)
            return success
        except Exception as e:
            self.log_test("Health Check", False, str(e))
            return False

    def test_auth_status_unauthenticated(self):
        """Test auth status endpoint when not authenticated"""
        try:
            response = requests.get(f"{self.api_base}/auth/status", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                expected_fields = ['authenticated']
                has_fields = all(field in data for field in expected_fields)
                success = has_fields and data['authenticated'] == False
                details += f", Authenticated: {data.get('authenticated')}, Has required fields: {has_fields}"
            
            self.log_test("Auth Status (Unauthenticated)", success, details)
            return success
        except Exception as e:
            self.log_test("Auth Status (Unauthenticated)", False, str(e))
            return False

    def test_github_login_url(self):
        """Test GitHub OAuth login URL endpoint"""
        try:
            response = requests.get(f"{self.api_base}/auth/github/login", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                expected_fields = ['auth_url']
                has_fields = all(field in data for field in expected_fields)
                auth_url = data.get('auth_url', '')
                is_github_url = 'github.com/login/oauth/authorize' in auth_url
                success = has_fields and is_github_url
                details += f", Has auth_url: {has_fields}, Is GitHub URL: {is_github_url}"
            
            self.log_test("GitHub Login URL", success, details)
            return success
        except Exception as e:
            self.log_test("GitHub Login URL", False, str(e))
            return False

    def test_signup_new_user(self):
        """Test user signup with email/password"""
        try:
            # Create unique test user
            timestamp = datetime.now().strftime('%H%M%S')
            test_user = {
                "email": f"test{timestamp}@example.com",
                "password": "password123",
                "username": f"testuser{timestamp}"
            }
            
            response = requests.post(f"{self.api_base}/auth/signup", json=test_user, timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                required_fields = ['token', 'user']
                has_fields = all(field in data for field in required_fields)
                user_data = data.get('user', {})
                user_fields = ['id', 'username', 'email']
                has_user_fields = all(field in user_data for field in user_fields)
                success = has_fields and has_user_fields and user_data.get('email') == test_user['email']
                details += f", Has required fields: {has_fields}, User fields: {has_user_fields}"
                
                # Store for login test
                self.test_user = test_user
                self.test_token = data.get('token')
            
            self.log_test("Signup New User", success, details)
            return success
        except Exception as e:
            self.log_test("Signup New User", False, str(e))
            return False

    def test_signup_existing_email(self):
        """Test signup with existing email (should fail)"""
        if not hasattr(self, 'test_user'):
            self.log_test("Signup Existing Email", False, "No test user created in previous test")
            return False
            
        try:
            # Try to signup with same email but different username
            duplicate_user = {
                "email": self.test_user['email'],  # Same email
                "password": "differentpass",
                "username": "differentuser"
            }
            
            response = requests.post(f"{self.api_base}/auth/signup", json=duplicate_user, timeout=10)
            success = response.status_code == 400  # Should fail with 400
            details = f"Status: {response.status_code} (Expected 400 for duplicate email)"
            
            if response.status_code == 400:
                data = response.json()
                error_message = data.get('detail', '')
                success = 'email' in error_message.lower() or 'already' in error_message.lower()
                details += f", Error message contains 'email' or 'already': {success}"
            
            self.log_test("Signup Existing Email (Should Fail)", success, details)
            return success
        except Exception as e:
            self.log_test("Signup Existing Email (Should Fail)", False, str(e))
            return False

    def test_login_valid_credentials(self):
        """Test login with valid email/password"""
        if not hasattr(self, 'test_user'):
            self.log_test("Login Valid Credentials", False, "No test user available")
            return False
            
        try:
            login_data = {
                "email": self.test_user['email'],
                "password": self.test_user['password']
            }
            
            response = requests.post(f"{self.api_base}/auth/login", json=login_data, timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                required_fields = ['token', 'user']
                has_fields = all(field in data for field in required_fields)
                user_data = data.get('user', {})
                success = has_fields and user_data.get('email') == self.test_user['email']
                details += f", Has required fields: {has_fields}, Email matches: {success}"
                
                # Store token for authenticated tests
                self.auth_token = data.get('token')
            
            self.log_test("Login Valid Credentials", success, details)
            return success
        except Exception as e:
            self.log_test("Login Valid Credentials", False, str(e))
            return False

    def test_login_invalid_password(self):
        """Test login with wrong password (should fail)"""
        if not hasattr(self, 'test_user'):
            self.log_test("Login Invalid Password", False, "No test user available")
            return False
            
        try:
            login_data = {
                "email": self.test_user['email'],
                "password": "wrongpassword123"
            }
            
            response = requests.post(f"{self.api_base}/auth/login", json=login_data, timeout=10)
            success = response.status_code == 401  # Should fail with 401
            details = f"Status: {response.status_code} (Expected 401 for wrong password)"
            
            if response.status_code == 401:
                data = response.json()
                error_message = data.get('detail', '')
                success = 'password' in error_message.lower() or 'invalid' in error_message.lower()
                details += f", Error message contains 'password' or 'invalid': {success}"
            
            self.log_test("Login Invalid Password (Should Fail)", success, details)
            return success
        except Exception as e:
            self.log_test("Login Invalid Password (Should Fail)", False, str(e))
            return False

    def test_login_nonexistent_email(self):
        """Test login with non-existent email (should fail)"""
        try:
            login_data = {
                "email": "nonexistent@example.com",
                "password": "somepassword"
            }
            
            response = requests.post(f"{self.api_base}/auth/login", json=login_data, timeout=10)
            success = response.status_code == 401  # Should fail with 401
            details = f"Status: {response.status_code} (Expected 401 for non-existent email)"
            
            self.log_test("Login Non-existent Email (Should Fail)", success, details)
            return success
        except Exception as e:
            self.log_test("Login Non-existent Email (Should Fail)", False, str(e))
            return False

    def test_auth_status_authenticated(self):
        """Test auth status endpoint when authenticated"""
        if not hasattr(self, 'auth_token'):
            self.log_test("Auth Status (Authenticated)", False, "No auth token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            response = requests.get(f"{self.api_base}/auth/status", headers=headers, timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                expected_fields = ['authenticated', 'user']
                has_fields = all(field in data for field in expected_fields)
                is_authenticated = data.get('authenticated') == True
                user_data = data.get('user', {})
                has_user_data = bool(user_data)
                success = has_fields and is_authenticated and has_user_data
                details += f", Authenticated: {is_authenticated}, Has user data: {has_user_data}"
            
            self.log_test("Auth Status (Authenticated)", success, details)
            return success
        except Exception as e:
            self.log_test("Auth Status (Authenticated)", False, str(e))
            return False

    def test_protected_endpoint_with_auth(self):
        """Test accessing protected endpoint with valid token"""
        if not hasattr(self, 'auth_token'):
            self.log_test("Protected Endpoint (With Auth)", False, "No auth token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            response = requests.get(f"{self.api_base}/settings", headers=headers, timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                # Should return settings data structure
                expected_fields = ['id', 'is_configured']
                has_fields = all(field in data for field in expected_fields)
                success = has_fields
                details += f", Has required fields: {has_fields}"
            
            self.log_test("Protected Endpoint (With Auth)", success, details)
            return success
        except Exception as e:
            self.log_test("Protected Endpoint (With Auth)", False, str(e))
            return False

    def test_get_settings(self):
        """Test get settings endpoint (should require auth)"""
        try:
            response = requests.get(f"{self.api_base}/settings", timeout=10)
            # Should return 401 when not authenticated
            success = response.status_code == 401
            details = f"Status: {response.status_code} (Expected 401 for unauthenticated request)"
            self.log_test("Get Settings (Requires Auth)", success, details)
            return success
        except Exception as e:
            self.log_test("Get Settings (Requires Auth)", False, str(e))
            return False

    def test_get_templates(self):
        """Test get templates endpoint"""
        try:
            response = requests.get(f"{self.api_base}/templates", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                # Should return 4 default templates
                expected_count = 4
                actual_count = len(data)
                success = actual_count == expected_count
                
                if success:
                    # Check template names
                    template_names = [t['name'] for t in data]
                    expected_names = ["Agent Persona", "Task Executor", "Knowledge Expert", "Minimal Prompt"]
                    has_all_names = all(name in template_names for name in expected_names)
                    success = has_all_names
                    details += f", Count: {actual_count}, Names: {template_names}"
                else:
                    details += f", Expected: {expected_count}, Got: {actual_count}"
            self.log_test("Get Templates (4 defaults)", success, details)
            return success, data if success else []
        except Exception as e:
            self.log_test("Get Templates (4 defaults)", False, str(e))
            return False, []

    def test_create_api_key(self):
        """Test create API key endpoint"""
        try:
            test_key_name = f"Test Key {datetime.now().strftime('%H%M%S')}"
            payload = {"name": test_key_name}
            response = requests.post(f"{self.api_base}/keys", json=payload, timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                required_fields = ['id', 'name', 'key', 'key_preview', 'created_at']
                has_fields = all(field in data for field in required_fields)
                success = has_fields and data['name'] == test_key_name
                if success:
                    self.api_key = data['key']  # Store for later tests
                details += f", Has required fields: {has_fields}, Name matches: {data.get('name') == test_key_name}"
            
            self.log_test("Create API Key", success, details)
            return success
        except Exception as e:
            self.log_test("Create API Key", False, str(e))
            return False

    def test_get_api_keys(self):
        """Test get API keys endpoint"""
        try:
            response = requests.get(f"{self.api_base}/keys", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                success = isinstance(data, list) and len(data) >= 1  # Should have at least the one we created
                details += f", Keys count: {len(data)}, Is list: {isinstance(data, list)}"
            
            self.log_test("Get API Keys", success, details)
            return success, data if success else []
        except Exception as e:
            self.log_test("Get API Keys", False, str(e))
            return False, []

    def test_delete_api_key(self, keys_data):
        """Test delete API key endpoint"""
        if not keys_data:
            self.log_test("Delete API Key", False, "No keys available to delete")
            return False
            
        try:
            # Delete the first key
            key_to_delete = keys_data[0]
            response = requests.delete(f"{self.api_base}/keys/{key_to_delete['id']}", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                # Verify it was deleted by checking the list
                get_response = requests.get(f"{self.api_base}/keys", timeout=10)
                if get_response.status_code == 200:
                    remaining_keys = get_response.json()
                    deleted_key_ids = [k['id'] for k in remaining_keys]
                    success = key_to_delete['id'] not in deleted_key_ids
                    details += f", Key removed from list: {success}"
            
            self.log_test("Delete API Key", success, details)
            return success
        except Exception as e:
            self.log_test("Delete API Key", False, str(e))
            return False

    def test_root_endpoint(self):
        """Test root API endpoint"""
        try:
            response = requests.get(f"{self.api_base}/", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                expected_fields = ['message', 'version']
                has_fields = all(field in data for field in expected_fields)
                success = has_fields
                details += f", Has required fields: {has_fields}"
            
            self.log_test("Root API Endpoint", success, details)
            return success
        except Exception as e:
            self.log_test("Root API Endpoint", False, str(e))
            return False

    def run_all_tests(self):
        """Run all backend API tests"""
        print("🚀 Starting Prompt Manager API Tests...")
        print(f"Testing against: {self.base_url}")
        print("-" * 50)

        # Test basic endpoints
        self.test_health_check()
        self.test_root_endpoint()
        
        # Test auth endpoints
        self.test_auth_status_unauthenticated()
        self.test_github_login_url()
        self.test_get_settings()
        
        # Test templates
        templates_success, templates_data = self.test_get_templates()
        
        # Test API keys CRUD
        self.test_create_api_key()
        keys_success, keys_data = self.test_get_api_keys()
        if keys_success and keys_data:
            self.test_delete_api_key(keys_data)

        # Print summary
        print("-" * 50)
        print(f"📊 Tests completed: {self.tests_passed}/{self.tests_run} passed")
        
        if self.failed_tests:
            print("\n❌ Failed tests:")
            for test in self.failed_tests:
                print(f"  - {test['name']}: {test['details']}")
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "failed_tests": self.failed_tests,
            "success_rate": (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        }

def main():
    tester = PromptManagerAPITester()
    results = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if results["passed_tests"] == results["total_tests"] else 1

if __name__ == "__main__":
    sys.exit(main())
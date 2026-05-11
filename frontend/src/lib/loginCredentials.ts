export function getLoginCredentials() {
  const testEmail = process.env.NEXT_PUBLIC_TEST_USER_EMAIL || "";
  const testPassword = process.env.NEXT_PUBLIC_TEST_USER_PASSWORD || "";
  const adminPasscode = process.env.NEXT_PUBLIC_ADMIN_PASSCODE || "";

  return {
    testUser: testEmail && testPassword
      ? { label: "Test user", email: testEmail, password: testPassword }
      : null,
    admin: adminPasscode
      ? { label: "Admin passcode", password: adminPasscode }
      : null,
  };
}

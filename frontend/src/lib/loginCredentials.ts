export function getLoginCredentials() {
  const adminPasscode = process.env.NEXT_PUBLIC_ADMIN_PASSCODE || "";

  return {
    admin: adminPasscode
      ? { label: "Admin passcode", password: adminPasscode }
      : null,
  };
}

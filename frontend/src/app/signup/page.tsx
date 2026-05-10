"use client";

import { useRouter } from "next/navigation";
import { AuthScreen } from "@/components/AuthScreen";

export default function SignUpPage() {
  const router = useRouter();

  return (
    <AuthScreen
      initialMode="register"
      onAuthenticated={() => {
        router.replace("/");
      }}
    />
  );
}

import { Suspense } from "react";
import { ClientLogin } from "./ClientLogin";

export default function ClientLoginPage() {
  return (
    <Suspense fallback={<main className="client-login"><div className="client-loading">Loading sign in...</div></main>}>
      <ClientLogin />
    </Suspense>
  );
}

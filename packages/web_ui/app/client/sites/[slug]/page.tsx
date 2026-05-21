import { ClientSitePage } from "./ClientSitePage";

export default async function ClientSiteRoute({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <ClientSitePage slug={slug} />;
}

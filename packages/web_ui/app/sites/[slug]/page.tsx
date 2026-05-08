import DashboardClient from "./DashboardClient";

export default async function SiteDashboardPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <DashboardClient slug={slug} />;
}

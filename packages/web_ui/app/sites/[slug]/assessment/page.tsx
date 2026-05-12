import DashboardClient from "../DashboardClient";

export default async function SiteAssessmentPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <DashboardClient slug={slug} variant="assessment" />;
}

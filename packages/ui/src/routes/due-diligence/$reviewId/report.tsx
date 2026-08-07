import { createFileRoute } from '@tanstack/react-router';
import { ReportViewer } from '../../../components/PortfolioDD/ReportViewer';

export const Route = createFileRoute('/portfolio-dd/$reviewId/report')({
  component: ReportViewer,
});

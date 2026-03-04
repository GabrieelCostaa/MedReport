import { Routes, Route, Navigate } from 'react-router-dom';
import { Box } from '@chakra-ui/react';
import Layout from './components/Layout';
import Login from './pages/Login';
import LegalBasis from './pages/LegalBasis';
import ReportList from './pages/ReportList';
import ReportCreate from './pages/ReportCreate';
import ReportReview from './pages/ReportReview';
import QuotesDashboard from './pages/QuotesDashboard';

function App() {
  return (
    <Box minH="100vh" bg="gray.50">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/legal-basis" element={<LegalBasis />} />
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/reports" replace />} />
          <Route path="reports" element={<ReportList />} />
          <Route path="reports/new" element={<ReportCreate />} />
          <Route path="reports/:id/review" element={<ReportReview />} />
          <Route path="quotes" element={<QuotesDashboard />} />
        </Route>
        <Route path="*" element={<Navigate to="/reports" replace />} />
      </Routes>
    </Box>
  );
}

export default App;

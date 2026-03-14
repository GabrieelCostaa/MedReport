import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Box, Spinner, Flex } from '@chakra-ui/react';
import Layout from './components/Layout';
import Login from './pages/Login';
import LegalBasis from './pages/LegalBasis';

const Home = lazy(() => import('./pages/Home'));
const ReportList = lazy(() => import('./pages/ReportList'));
const ReportCreate = lazy(() => import('./pages/ReportCreate'));
const ReportReview = lazy(() => import('./pages/ReportReview'));
const QuotesDashboard = lazy(() => import('./pages/QuotesDashboard'));

function PageLoader() {
  return (
    <Flex justify="center" align="center" minH="200px">
      <Spinner size="lg" color="brand.500" thickness="3px" />
    </Flex>
  );
}

function App() {
  return (
    <Box minH="100vh" bg="#f8fafc">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/legal-basis" element={<LegalBasis />} />
        <Route path="/" element={<Layout />}>
          <Route index element={<Suspense fallback={<PageLoader />}><Home /></Suspense>} />
          <Route path="reports" element={<Suspense fallback={<PageLoader />}><ReportList /></Suspense>} />
          <Route path="reports/new" element={<Suspense fallback={<PageLoader />}><ReportCreate /></Suspense>} />
          <Route path="reports/:id/review" element={<Suspense fallback={<PageLoader />}><ReportReview /></Suspense>} />
          <Route path="quotes" element={<Suspense fallback={<PageLoader />}><QuotesDashboard /></Suspense>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Box>
  );
}

export default App;

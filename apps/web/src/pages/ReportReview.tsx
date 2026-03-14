import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Heading,
  Text,
  VStack,
  useToast,
  Badge,
  HStack,
} from '@chakra-ui/react';
import { reportsApi } from '../api/reports';

type ReportDetail = {
  id: string;
  status: string;
  cid?: string;
  diagnosis?: string;
  surgery_description?: string;
  materials?: string;
  health_plan?: string;
  created_at: string;
  inconsistencies?: { field: string; message: string }[];
};

export default function ReportReview() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [signing, setSigning] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    if (!id) return;
    reportsApi
      .get(id)
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDownloadPdf = async () => {
    if (!id) return;
    try {
      const blob = await reportsApi.downloadPdf(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `relatorio-${id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: 'Erro ao baixar PDF', status: 'error' });
    }
  };

  const handleDownloadXml = async () => {
    if (!id) return;
    try {
      const blob = await reportsApi.downloadXml(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `guia-tiss-${id}.xml`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: 'Erro ao baixar XML', status: 'error' });
    }
  };

  const handleDownloadDocx = async () => {
    if (!id) return;
    try {
      const blob = await reportsApi.downloadDocx(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `relatorio-${id}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: 'Erro ao baixar DOCX', status: 'error' });
    }
  };

  const handleSign = async () => {
    if (!id) return;
    setSigning(true);
    try {
      await reportsApi.sign(id);
      toast({ title: 'Relatório assinado', status: 'success' });
      setReport((p) => (p ? { ...p, status: 'signed' } : null));
    } catch {
      toast({ title: 'Erro ao assinar (integre ICP-Brasil)', status: 'error' });
    } finally {
      setSigning(false);
    }
  };

  if (loading || !report) {
    return <Box>Carregando...</Box>;
  }

  return (
    <Box>
      <HStack justify="space-between" mb={6} flexWrap="wrap" gap={3}>
        <Box>
          <Heading size="md" fontWeight="700" color="gray.800">
            Revisao do Relatorio
          </Heading>
          <HStack mt={2} gap={3}>
            <Badge
              colorScheme={report.status === 'signed' ? 'green' : 'yellow'}
              fontSize="xs"
              borderRadius="full"
              px={2}
              py={0.5}
            >
              {report.status === 'signed' ? 'Assinado' : 'Rascunho'}
            </Badge>
            <Text fontSize="xs" color="gray.400">
              Criado em {new Date(report.created_at).toLocaleDateString('pt-BR', {
                day: '2-digit', month: 'short', year: 'numeric',
                hour: '2-digit', minute: '2-digit',
              })}
            </Text>
          </HStack>
        </Box>
        <Button variant="ghost" size="sm" color="gray.500" onClick={() => navigate('/dashboard/reports')}>
          Voltar aos documentos
        </Button>
      </HStack>

      <Box p={5} bg="white" borderRadius="xl" border="1px solid" borderColor="gray.100" maxW="2xl" mb={6}>
        <VStack align="stretch" gap={4}>
          <HStack gap={8} flexWrap="wrap">
            <Box>
              <Text fontSize="xs" fontWeight="600" color="gray.500" textTransform="uppercase" letterSpacing="wider">CID</Text>
              <Text fontSize="sm" fontWeight="500" mt={1}>{report.cid ?? '-'}</Text>
            </Box>
            <Box>
              <Text fontSize="xs" fontWeight="600" color="gray.500" textTransform="uppercase" letterSpacing="wider">Convenio</Text>
              <Text fontSize="sm" fontWeight="500" mt={1}>{report.health_plan ?? 'Nao informado'}</Text>
            </Box>
          </HStack>
          <Box>
            <Text fontSize="xs" fontWeight="600" color="gray.500" textTransform="uppercase" letterSpacing="wider">Diagnostico</Text>
            <Text fontSize="sm" mt={1}>{report.diagnosis ?? '-'}</Text>
          </Box>
          <Box>
            <Text fontSize="xs" fontWeight="600" color="gray.500" textTransform="uppercase" letterSpacing="wider">Procedimento</Text>
            <Text fontSize="sm" mt={1}>{report.surgery_description ?? '-'}</Text>
          </Box>
          <Box>
            <Text fontSize="xs" fontWeight="600" color="gray.500" textTransform="uppercase" letterSpacing="wider">Materiais OPME</Text>
            <Text fontSize="sm" mt={1}>{report.materials ?? '-'}</Text>
          </Box>
        </VStack>
      </Box>

      {report.inconsistencies && report.inconsistencies.length > 0 && (
        <Box p={4} bg="orange.50" borderRadius="xl" border="1px solid" borderColor="orange.200" mb={6} maxW="2xl">
          <Text fontWeight="600" fontSize="sm" color="orange.800" mb={2}>
            Inconsistencias TUSS
          </Text>
          <VStack align="stretch" gap={1}>
            {report.inconsistencies.map((inc, i) => (
              <Text key={i} fontSize="sm" color="orange.700">
                {inc.field}: {inc.message}
              </Text>
            ))}
          </VStack>
        </Box>
      )}

      <HStack gap={3} flexWrap="wrap">
        <Button onClick={handleDownloadPdf} variant="outline" size="sm" borderRadius="lg">
          Baixar PDF
        </Button>
        <Button onClick={handleDownloadDocx} variant="outline" size="sm" borderRadius="lg">
          Baixar Word
        </Button>
        <Button onClick={handleDownloadXml} variant="outline" size="sm" borderRadius="lg">
          Baixar XML (TISS)
        </Button>
        {report.status !== 'signed' && (
          <Button colorScheme="brand" onClick={handleSign} isLoading={signing} size="sm" borderRadius="lg" fontWeight="600">
            Assinar digitalmente
          </Button>
        )}
      </HStack>
    </Box>
  );
}

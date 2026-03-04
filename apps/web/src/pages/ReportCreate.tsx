import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Input,
  Textarea,
  VStack,
  Heading,
  useToast,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
} from '@chakra-ui/react';
import { reportsApi } from '../api/reports';
import { tussApi } from '../api/tuss';
import ReportAssistant from '../components/ReportAssistant';

export default function ReportCreate() {
  const [formData, setFormData] = useState({
    cid: '',
    diagnosis: '',
    surgery_description: '',
    materials: '',
    health_plan: '',
  });
  const [suggestions, setSuggestions] = useState<{ code: string; term: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();

  const handleSearchTuss = async () => {
    if (!formData.surgery_description.trim()) return;
    setSearching(true);
    try {
      const res = await tussApi.search(formData.surgery_description);
      setSuggestions(res.items ?? []);
    } catch {
      setSuggestions([]);
    } finally {
      setSearching(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const report = await reportsApi.create(formData);
      toast({ title: 'Relatório criado', status: 'success' });
      navigate(`/reports/${report.id}/review`);
    } catch {
      toast({ title: 'Erro ao criar relatório', status: 'error' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      <Heading size="md" mb={6}>
        Novo relatório de solicitação de cirurgia
      </Heading>
      <Tabs>
        <TabList>
          <Tab>Formulário</Tab>
          <Tab>Assistente (chat)</Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <form onSubmit={handleSubmit}>
              <VStack gap={4} align="stretch" maxW="2xl">
                <FormControl isRequired>
                  <FormLabel>CID</FormLabel>
                  <Input
                    value={formData.cid}
                    onChange={(e) => setFormData((p) => ({ ...p, cid: e.target.value }))}
                    placeholder="Ex: M17.9"
                  />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Diagnóstico</FormLabel>
                  <Textarea
                    value={formData.diagnosis}
                    onChange={(e) => setFormData((p) => ({ ...p, diagnosis: e.target.value }))}
                    placeholder="Descrição do diagnóstico"
                  />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Descrição da cirurgia</FormLabel>
                  <Textarea
                    value={formData.surgery_description}
                    onChange={(e) =>
                      setFormData((p) => ({ ...p, surgery_description: e.target.value }))
                    }
                    placeholder="Ex: Artroplastia de joelho"
                  />
                  <Button
                    size="sm"
                    mt={2}
                    variant="outline"
                    onClick={handleSearchTuss}
                    isLoading={searching}
                  >
                    Buscar códigos TUSS
                  </Button>
                </FormControl>
                {suggestions.length > 0 && (
                  <Box p={3} bg="gray.50" borderRadius="md">
                    <strong>Sugestões TUSS:</strong>
                    <VStack align="stretch" mt={2}>
                      {suggestions.slice(0, 5).map((s, i) => (
                        <Box key={i} fontSize="sm">
                          {s.code} – {s.term}
                        </Box>
                      ))}
                    </VStack>
                  </Box>
                )}
                <FormControl>
                  <FormLabel>Materiais / OPME</FormLabel>
                  <Textarea
                    value={formData.materials}
                    onChange={(e) => setFormData((p) => ({ ...p, materials: e.target.value }))}
                    placeholder="Materiais necessários"
                  />
                </FormControl>
                <FormControl>
                  <FormLabel>Convênio</FormLabel>
                  <Input
                    value={formData.health_plan}
                    onChange={(e) => setFormData((p) => ({ ...p, health_plan: e.target.value }))}
                    placeholder="Nome do plano"
                  />
                </FormControl>
                <Button type="submit" colorScheme="green" isLoading={loading}>
                  Gerar relatório (guia TISS)
                </Button>
              </VStack>
            </form>
          </TabPanel>
          <TabPanel>
            <ReportAssistant onReportCreated={(id) => navigate(`/reports/${id}/review`)} />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}

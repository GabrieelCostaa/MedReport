import {
  VStack,
  HStack,
  Box,
  Flex,
  FormControl,
  FormLabel,
  Input,
  Heading,
  Text,
  Button,
  Badge,
  Spinner,
} from '@chakra-ui/react';
import type { Product } from '../types';

interface StepPacienteProps {
  pacienteNome: string;
  onPacienteNomeChange: (value: string) => void;
  healthPlan: string;
  onHealthPlanChange: (value: string) => void;
  pacienteDob: string;
  onPacienteDobChange: (value: string) => void;
  pacienteCarteirinha: string;
  onPacienteCarteirinhaChange: (value: string) => void;
  guiaNumero: string;
  onGuiaNumeroChange: (value: string) => void;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  loadingProducts: boolean;
  products: Product[];
  selectedProduct: Product | null;
  onSelectProduct: (p: Product) => void;
  onClearProduct: () => void;
  showQuickRegister: boolean;
  onShowQuickRegister: (show: boolean) => void;
  quickName: string;
  onQuickNameChange: (value: string) => void;
  quickAnvisa: string;
  onQuickAnvisaChange: (value: string) => void;
  quickFabricante: string;
  onQuickFabricanteChange: (value: string) => void;
  quickTuss: string;
  onQuickTussChange: (value: string) => void;
  savingProduct: boolean;
  onQuickRegister: () => void;
  onBack: () => void;
  onNext: () => void;
}

export default function StepPaciente({
  pacienteNome,
  onPacienteNomeChange,
  healthPlan,
  onHealthPlanChange,
  pacienteDob,
  onPacienteDobChange,
  pacienteCarteirinha,
  onPacienteCarteirinhaChange,
  guiaNumero,
  onGuiaNumeroChange,
  searchQuery,
  onSearchQueryChange,
  loadingProducts,
  products,
  selectedProduct,
  onSelectProduct,
  onClearProduct,
  showQuickRegister,
  onShowQuickRegister,
  quickName,
  onQuickNameChange,
  quickAnvisa,
  onQuickAnvisaChange,
  quickFabricante,
  onQuickFabricanteChange,
  quickTuss,
  onQuickTussChange,
  savingProduct,
  onQuickRegister,
  onBack,
  onNext,
}: StepPacienteProps) {
  return (
    <Flex justify="center" w="100%">
      <VStack gap={5} align="stretch" maxW="2xl" mx="auto" w="100%">
        {/* Header */}
        <Box>
          <Text
            fontSize="sm"
            fontWeight="600"
            color="brand.text"
            letterSpacing="wide"
            textTransform="uppercase"
          >
            Passo 2 — Paciente & Material OPME
          </Text>
        </Box>

        {/* Main form card */}
        <Box
          bg="surface"
          p={6}
          borderRadius="xl"
          border="1px solid"
          borderColor="border.subtle"
          shadow="sm"
        >
          <VStack gap={4} align="stretch">
            <FormControl isRequired>
              <FormLabel fontWeight="500" color="text.secondary">Nome do Paciente</FormLabel>
              <Input
                value={pacienteNome}
                onChange={(e) => onPacienteNomeChange(e.target.value)}
                placeholder="Nome completo"
                borderRadius="lg"
              />
            </FormControl>

            <FormControl>
              <FormLabel fontWeight="500" color="text.secondary">Convenio</FormLabel>
              <Input
                value={healthPlan}
                onChange={(e) => onHealthPlanChange(e.target.value)}
                placeholder="Nome do convenio"
                borderRadius="lg"
              />
            </FormControl>

            {/* Dados de autorização (opcionais) — reduzem risco de glosa */}
            <HStack gap={3} align="start">
              <FormControl>
                <FormLabel fontWeight="500" color="text.secondary" fontSize="sm">
                  Data de nascimento
                </FormLabel>
                <Input
                  type="date"
                  value={pacienteDob}
                  onChange={(e) => onPacienteDobChange(e.target.value)}
                  borderRadius="lg"
                />
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="500" color="text.secondary" fontSize="sm">
                  Carteirinha do convênio
                </FormLabel>
                <Input
                  value={pacienteCarteirinha}
                  onChange={(e) => onPacienteCarteirinhaChange(e.target.value)}
                  placeholder="Nº da carteirinha"
                  borderRadius="lg"
                />
              </FormControl>
            </HStack>

            <FormControl>
              <FormLabel fontWeight="500" color="text.secondary" fontSize="sm">
                Nº da guia (opcional)
              </FormLabel>
              <Input
                value={guiaNumero}
                onChange={(e) => onGuiaNumeroChange(e.target.value)}
                placeholder="Nº da guia de solicitação TISS"
                borderRadius="lg"
              />
            </FormControl>
          </VStack>
        </Box>

        {/* Material OPME card */}
        <Box
          bg="surface"
          p={6}
          borderRadius="xl"
          border="1px solid"
          borderColor="border.subtle"
          shadow="sm"
        >
          <VStack gap={4} align="stretch">
            <FormControl>
              <FormLabel fontWeight="500" color="text.secondary">Material OPME</FormLabel>
              <Input
                value={searchQuery}
                onChange={(e) => onSearchQueryChange(e.target.value)}
                placeholder="Digite para buscar o produto..."
                borderRadius="lg"
              />
              {loadingProducts && <Spinner size="xs" color="brand.text" mt={2} />}
            </FormControl>

            {/* No products found */}
            {products.length === 0 && !loadingProducts && !showQuickRegister && (
              <Box p={4} bg="yellow.50" borderRadius="lg" border="1px solid" borderColor="yellow.200">
                <Text color="yellow.800" fontSize="sm" fontWeight="500" mb={2}>
                  Nenhum produto encontrado no catalogo.
                </Text>
                <Button
                  size="sm"
                  colorScheme="brand"
                  variant="outline"
                  borderRadius="lg"
                  transition="all 0.3s cubic-bezier(0.65, 0.05, 0, 1)"
                  _hover={{ transform: 'translateY(-2px)', shadow: 'lg' }}
                  onClick={() => onShowQuickRegister(true)}
                >
                  Cadastrar novo produto
                </Button>
              </Box>
            )}

            {/* Quick product registration form */}
            {showQuickRegister && (
              <Box p={5} bg="brand.surface" borderRadius="xl" border="1px solid" borderColor="brand.border">
                <HStack justify="space-between" mb={4}>
                  <Heading size="sm" color="brand.text">Cadastro Rapido de Produto</Heading>
                  <Button size="xs" variant="ghost" onClick={() => onShowQuickRegister(false)}>Cancelar</Button>
                </HStack>
                <VStack gap={3} align="stretch">
                  <FormControl isRequired>
                    <FormLabel fontSize="sm">Nome do Material</FormLabel>
                    <Input
                      size="sm"
                      bg="surface"
                      borderRadius="lg"
                      value={quickName}
                      onChange={(e) => onQuickNameChange(e.target.value)}
                      placeholder="Ex: Protese total de joelho cimentada"
                    />
                  </FormControl>
                  <HStack gap={3}>
                    <FormControl>
                      <FormLabel fontSize="sm">Registro ANVISA</FormLabel>
                      <Input
                        size="sm"
                        bg="surface"
                        borderRadius="lg"
                        value={quickAnvisa}
                        onChange={(e) => onQuickAnvisaChange(e.target.value)}
                        placeholder="Ex: 80102710068"
                      />
                    </FormControl>
                    <FormControl>
                      <FormLabel fontSize="sm">Fabricante</FormLabel>
                      <Input
                        size="sm"
                        bg="surface"
                        borderRadius="lg"
                        value={quickFabricante}
                        onChange={(e) => onQuickFabricanteChange(e.target.value)}
                        placeholder="Ex: Zimmer Biomet"
                      />
                    </FormControl>
                  </HStack>
                  <FormControl>
                    <FormLabel fontSize="sm">Codigo TUSS (opcional)</FormLabel>
                    <Input
                      size="sm"
                      bg="surface"
                      borderRadius="lg"
                      value={quickTuss}
                      onChange={(e) => onQuickTussChange(e.target.value)}
                      placeholder="Ex: 30715016"
                    />
                  </FormControl>
                  <Button
                    colorScheme="brand"
                    size="sm"
                    borderRadius="lg"
                    transition="all 0.3s cubic-bezier(0.65, 0.05, 0, 1)"
                    _hover={{ transform: 'translateY(-2px)', shadow: 'lg' }}
                    onClick={onQuickRegister}
                    isLoading={savingProduct}
                  >
                    Salvar e Selecionar
                  </Button>
                </VStack>
              </Box>
            )}

            {/* Selected product indicator */}
            {selectedProduct && !showQuickRegister && (
              <Box p={3} bg="brand.surface" borderRadius="lg" border="1px solid" borderColor="brand.border">
                <HStack justify="space-between">
                  <HStack>
                    <Box w="8px" h="8px" borderRadius="full" bg="brand.text" />
                    <Text fontSize="sm" fontWeight="600" color="brand.text">{selectedProduct.nome}</Text>
                    {selectedProduct.registro_anvisa && (
                      <Badge colorScheme="brand" fontSize="2xs">ANVISA: {selectedProduct.registro_anvisa}</Badge>
                    )}
                  </HStack>
                  <Button size="xs" variant="ghost" color="text.muted" onClick={onClearProduct}>Trocar</Button>
                </HStack>
              </Box>
            )}

            {/* Product list */}
            {!selectedProduct && !showQuickRegister && products.length > 0 && (
              <VStack align="stretch" gap={2} maxH="300px" overflowY="auto">
                {products.map((p) => (
                  <Box
                    key={p.id}
                    p={4}
                    border="1px solid"
                    borderColor="border.muted"
                    borderRadius="lg"
                    cursor="pointer"
                    onClick={() => onSelectProduct(p)}
                    bg="surface"
                    transition="all 0.2s ease"
                    _hover={{
                      borderColor: 'brand.300',
                      bg: 'brand.surface',
                      shadow: 'sm',
                    }}
                  >
                    <HStack justify="space-between">
                      <Box flex={1}>
                        <HStack gap={2} flexWrap="wrap">
                          <Text fontWeight="bold" fontSize="sm">{p.nome}</Text>
                          {p.source === 'anvisa' && (
                            <Badge colorScheme="purple" fontSize="2xs">ANVISA</Badge>
                          )}
                          {p.classe_risco && (
                            <Badge colorScheme="orange" fontSize="2xs">Classe {p.classe_risco}</Badge>
                          )}
                        </HStack>
                        {p.linha && <Text fontSize="xs" color="text.muted" mt={1}>{p.linha}</Text>}
                      </Box>
                      {p.registro_anvisa && <Text fontSize="xs" color="text.subtle">Reg: {p.registro_anvisa}</Text>}
                    </HStack>
                    {p.diferenciais_clinicos && (
                      <Text fontSize="sm" color="gray.600" mt={1} noOfLines={2}>{p.diferenciais_clinicos}</Text>
                    )}
                    {p.codigo_tuss_sugerido && (
                      <Text fontSize="xs" color="text.subtle" mt={1}>TUSS: {p.codigo_tuss_sugerido}</Text>
                    )}
                  </Box>
                ))}
              </VStack>
            )}

            {!selectedProduct && !showQuickRegister && products.length > 0 && (
              <Button
                size="sm"
                variant="link"
                color="brand.600"
                onClick={() => onShowQuickRegister(true)}
              >
                Nao encontrou? Cadastrar novo produto
              </Button>
            )}
          </VStack>
        </Box>

        {/* Action buttons */}
        <HStack justify="flex-end" pt={2}>
          <Button
            variant="outline"
            borderColor="gray.300"
            borderRadius="lg"
            transition="all 0.3s cubic-bezier(0.65, 0.05, 0, 1)"
            _hover={{ bg: 'gray.50' }}
            onClick={onBack}
          >
            Voltar
          </Button>
          <Button
            colorScheme="brand"
            borderRadius="lg"
            transition="all 0.3s cubic-bezier(0.65, 0.05, 0, 1)"
            _hover={{ transform: 'translateY(-2px)', shadow: 'lg' }}
            onClick={onNext}
            isDisabled={!selectedProduct}
          >
            Gerar Justificativa com IA
          </Button>
        </HStack>
      </VStack>
    </Flex>
  );
}

import { useEffect, useState } from 'react';
import { useNavigate, Link as RouterLink } from 'react-router-dom';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Input,
  VStack,
  Text,
  useToast,
  HStack,
  Link,
  Select,
} from '@chakra-ui/react';
import { authApi } from '../api/auth';

const UFS_BRASIL = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO',
  'MA','MT','MS','MG','PA','PB','PR','PE','PI',
  'RJ','RN','RS','RO','RR','SC','SP','SE','TO',
];

export default function Register() {
  const [nome, setNome] = useState('');
  const [crm, setCrm] = useState('');
  const [crmUf, setCrmUf] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [testingMode, setTestingMode] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    authApi.config().then((c) => setTestingMode(c.testing_mode)).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      toast({ title: 'As senhas não coincidem', status: 'error' });
      return;
    }
    if (password.length < 6) {
      toast({ title: 'A senha deve ter pelo menos 6 caracteres', status: 'error' });
      return;
    }
    if (!testingMode) {
      if (!nome.trim()) {
        toast({ title: 'Nome completo é obrigatório', status: 'error' });
        return;
      }
      if (!/^\d{4,8}$/.test(crm)) {
        toast({ title: 'CRM inválido. Use apenas dígitos (4-8 caracteres)', status: 'error' });
        return;
      }
      if (!crmUf) {
        toast({ title: 'Selecione a UF do CRM', status: 'error' });
        return;
      }
    }
    setLoading(true);
    try {
      const res = testingMode
        ? await authApi.register(email, password)
        : await authApi.register(email, password, nome, crm, crmUf);
      localStorage.setItem('token', res.access_token);
      localStorage.setItem('user', JSON.stringify(res.user));
      toast({
        title: 'Conta criada com sucesso!',
        status: 'success',
        duration: 3000,
      });
      navigate(res.user.legal_basis_acknowledged ? '/dashboard' : '/legal-basis');
    } catch (err: unknown) {
      toast({
        title: 'Erro no cadastro',
        description: (err as { message?: string })?.message ?? 'Tente novamente.',
        status: 'error',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box minH="100vh" bg="#f8fafc" display="flex" alignItems="center" justifyContent="center">
      <Box w="full" maxW="400px" mx={4} py={8}>
        {/* Logo */}
        <VStack mb={8}>
          <HStack gap={2}>
            <Box
              w="44px"
              h="44px"
              borderRadius="xl"
              bg="brand.500"
              display="flex"
              alignItems="center"
              justifyContent="center"
              color="white"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L12 6" />
                <path d="M12 18L12 22" />
                <path d="M9 6C9 4.34 10.34 3 12 3s3 1.34 3 3-1.34 3-3 3" />
                <path d="M15 6c0 1.66-1.34 3-3 3" />
                <path d="M9 9v4c0 1 .6 3 3 3s3-2 3-3V9" />
                <path d="M8 18h8" />
              </svg>
            </Box>
            <Box>
              <Text fontSize="xl" fontWeight="700" color="medical.500" letterSpacing="-0.02em" lineHeight="1">
                MedReport
              </Text>
              <Text fontSize="xs" color="gray.400" fontWeight="500" mt="2px">
                Justificativas OPME Inteligentes
              </Text>
            </Box>
          </HStack>
        </VStack>

        {/* Form */}
        <Box p={8} bg="white" borderRadius="xl" border="1px solid" borderColor="gray.100" shadow="sm">
          <Text fontSize="lg" fontWeight="600" mb={1} color="gray.800">
            Criar conta
          </Text>
          <Text fontSize="sm" color="gray.500" mb={6}>
            Cadastre-se para gerar seus relatórios
          </Text>

          <form onSubmit={handleSubmit}>
            <VStack gap={4} align="stretch">
              {!testingMode && (
                <>
                  {/* Nome */}
                  <FormControl isRequired>
                    <FormLabel fontSize="sm" fontWeight="500" color="gray.700">Nome completo</FormLabel>
                    <Input
                      type="text"
                      value={nome}
                      onChange={(e) => setNome(e.target.value)}
                      placeholder="Dr. João da Silva"
                      size="lg"
                      fontSize="sm"
                      borderRadius="lg"
                    />
                  </FormControl>

                  {/* CRM + UF */}
                  <HStack gap={3} align="flex-end">
                    <FormControl isRequired flex={1}>
                      <FormLabel fontSize="sm" fontWeight="500" color="gray.700">CRM</FormLabel>
                      <Input
                        type="text"
                        inputMode="numeric"
                        value={crm}
                        onChange={(e) => setCrm(e.target.value.replace(/\D/g, '').slice(0, 8))}
                        placeholder="123456"
                        size="lg"
                        fontSize="sm"
                        borderRadius="lg"
                      />
                    </FormControl>
                    <FormControl isRequired w="110px">
                      <FormLabel fontSize="sm" fontWeight="500" color="gray.700">UF</FormLabel>
                      <Select
                        value={crmUf}
                        onChange={(e) => setCrmUf(e.target.value)}
                        size="lg"
                        fontSize="sm"
                        borderRadius="lg"
                        placeholder="UF"
                      >
                        {UFS_BRASIL.map((uf) => (
                          <option key={uf} value={uf}>{uf}</option>
                        ))}
                      </Select>
                    </FormControl>
                  </HStack>
                </>
              )}

              {/* Email */}
              <FormControl isRequired>
                <FormLabel fontSize="sm" fontWeight="500" color="gray.700">E-mail</FormLabel>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="seu@email.com"
                  size="lg"
                  fontSize="sm"
                  borderRadius="lg"
                />
              </FormControl>

              {/* Senha */}
              <FormControl isRequired>
                <FormLabel fontSize="sm" fontWeight="500" color="gray.700">Senha</FormLabel>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={testingMode ? 'Mínimo 6 caracteres' : 'Mín. 8 chars: maiúscula, minúscula e número'}
                  size="lg"
                  fontSize="sm"
                  borderRadius="lg"
                />
              </FormControl>
              <FormControl isRequired>
                <FormLabel fontSize="sm" fontWeight="500" color="gray.700">Confirmar senha</FormLabel>
                <Input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  size="lg"
                  fontSize="sm"
                  borderRadius="lg"
                />
              </FormControl>

              <Button
                type="submit"
                colorScheme="brand"
                isLoading={loading}
                w="full"
                size="lg"
                fontSize="sm"
                fontWeight="600"
                borderRadius="lg"
                mt={2}
              >
                Criar conta
              </Button>
            </VStack>
          </form>
        </Box>

        <Text fontSize="sm" color="gray.500" textAlign="center" mt={6}>
          Já tem conta?{' '}
          <Link as={RouterLink} to="/login" color="brand.600" fontWeight="600">
            Entrar
          </Link>
        </Text>
      </Box>
    </Box>
  );
}

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
} from '@chakra-ui/react';
import { authApi } from '../api/auth';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await authApi.login(email, password);
      localStorage.setItem('token', res.access_token);
      localStorage.setItem('user', JSON.stringify(res.user));
      const nome = res.user.email?.split('@')[0] || '';
      toast({
        title: nome ? `Bem-vindo, Dr. ${nome}` : 'Login realizado',
        status: 'success',
        duration: 3000,
      });
      navigate(res.user.legal_basis_acknowledged ? '/dashboard' : '/legal-basis');
    } catch (err: unknown) {
      toast({
        title: 'Erro no login',
        description: (err as { message?: string })?.message ?? 'Tente novamente.',
        status: 'error',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box minH="100vh" bg="#f8fafc" display="flex" alignItems="center" justifyContent="center">
      <Box w="full" maxW="400px" mx={4}>
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
            Bem-vindo de volta
          </Text>
          <Text fontSize="sm" color="gray.500" mb={6}>
            Entre com suas credenciais para continuar
          </Text>

          <form onSubmit={handleSubmit}>
            <VStack gap={4} align="stretch">
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
              <FormControl isRequired>
                <FormLabel fontSize="sm" fontWeight="500" color="gray.700">Senha</FormLabel>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
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
                Entrar
              </Button>
            </VStack>
          </form>
        </Box>

        <Text fontSize="xs" color="gray.400" textAlign="center" mt={6}>
          Plataforma exclusiva para profissionais de saude
        </Text>
      </Box>
    </Box>
  );
}

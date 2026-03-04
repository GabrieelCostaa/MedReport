import { Outlet, Link as RouterLink, useNavigate } from 'react-router-dom';
import {
  Box,
  Flex,
  Link,
  Button,
  Heading,
  HStack,
  useColorModeValue,
} from '@chakra-ui/react';

export default function Layout() {
  const bg = useColorModeValue('white', 'gray.800');
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  return (
    <Box>
      <Flex
        as="header"
        bg={bg}
        px={6}
        py={4}
        shadow="sm"
        align="center"
        justify="space-between"
      >
        <Heading size="md" color="brand.600">
          OPME Platform
        </Heading>
        <HStack gap={4}>
          <Link as={RouterLink} to="/reports">
            Relatórios
          </Link>
          <Link as={RouterLink} to="/quotes">
            Cotações
          </Link>
          <Button size="sm" variant="outline" onClick={handleLogout}>
            Sair
          </Button>
        </HStack>
      </Flex>
      <Box as="main" p={6}>
        <Outlet />
      </Box>
    </Box>
  );
}

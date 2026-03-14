import { Outlet, Link as RouterLink, useNavigate, useLocation } from 'react-router-dom';
import {
  Box,
  Flex,
  Link,
  Button,
  HStack,
  Text,
  useColorMode,
  useColorModeValue,
  Avatar,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  IconButton,
} from '@chakra-ui/react';

function MedReportLogo() {
  return (
    <HStack gap={2} as={RouterLink} to="/" _hover={{ textDecoration: 'none' }}>
      <Box
        w="36px"
        h="36px"
        borderRadius="lg"
        bg="brand.500"
        display="flex"
        alignItems="center"
        justifyContent="center"
        color="white"
        fontWeight="bold"
        fontSize="lg"
        flexShrink={0}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2L12 6" />
          <path d="M12 18L12 22" />
          <path d="M9 6C9 4.34 10.34 3 12 3s3 1.34 3 3-1.34 3-3 3" />
          <path d="M15 6c0 1.66-1.34 3-3 3" />
          <path d="M9 9v4c0 1 .6 3 3 3s3-2 3-3V9" />
          <path d="M8 18h8" />
        </svg>
      </Box>
      <Box>
        <Text fontSize="md" fontWeight="700" color="medical.500" letterSpacing="-0.02em" lineHeight="1">
          MedReport
        </Text>
        <Text fontSize="2xs" color="gray.400" fontWeight="500" letterSpacing="0.05em" mt="1px">
          JUSTIFICATIVAS OPME
        </Text>
      </Box>
    </HStack>
  );
}

function NavLink({ to, children, isActive }: { to: string; children: React.ReactNode; isActive: boolean }) {
  return (
    <Link
      as={RouterLink}
      to={to}
      px={3}
      py={2}
      borderRadius="md"
      fontSize="sm"
      fontWeight="500"
      color={isActive ? 'brand.700' : 'gray.600'}
      bg={isActive ? 'brand.50' : 'transparent'}
      _hover={{ bg: isActive ? 'brand.50' : 'gray.50', color: 'brand.700', textDecoration: 'none' }}
      transition="all 0.15s"
    >
      {children}
    </Link>
  );
}

export default function Layout() {
  const bg = useColorModeValue('white', 'gray.800');
  const { colorMode, toggleColorMode } = useColorMode();
  const navigate = useNavigate();
  const location = useLocation();

  const user = (() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}'); }
    catch { return {}; }
  })();

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const isActive = (path: string) => location.pathname.startsWith(path);

  return (
    <Box minH="100vh">
      <Flex
        as="header"
        bg={bg}
        px={6}
        py={3}
        borderBottom="1px solid"
        borderColor="gray.100"
        align="center"
        justify="space-between"
        position="sticky"
        top={0}
        zIndex={10}
      >
        <HStack gap={8}>
          <MedReportLogo />
          <HStack gap={1} display={{ base: 'none', md: 'flex' }}>
            <NavLink to="/" isActive={location.pathname === '/'}>
              Inicio
            </NavLink>
            <NavLink to="/reports" isActive={isActive('/reports')}>
              Documentos
            </NavLink>
            <NavLink to="/quotes" isActive={isActive('/quotes')}>
              Cotacoes
            </NavLink>
          </HStack>
        </HStack>

        <HStack gap={3}>
          <IconButton
            aria-label="Alternar tema"
            variant="ghost"
            size="sm"
            onClick={toggleColorMode}
            icon={
              colorMode === 'light' ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="5" />
                  <line x1="12" y1="1" x2="12" y2="3" />
                  <line x1="12" y1="21" x2="12" y2="23" />
                  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                  <line x1="1" y1="12" x2="3" y2="12" />
                  <line x1="21" y1="12" x2="23" y2="12" />
                  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
                </svg>
              )
            }
          />
          <Button
            as={RouterLink}
            to="/reports/new"
            size="sm"
            colorScheme="brand"
            fontWeight="600"
            leftIcon={
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M12 5v14M5 12h14" />
              </svg>
            }
          >
            Novo Relatorio
          </Button>
          <Menu>
            <MenuButton
              as={IconButton}
              aria-label="Menu do usuario"
              variant="ghost"
              size="sm"
              icon={
                <Avatar
                  size="sm"
                  name={user.email || 'U'}
                  bg="brand.500"
                  color="white"
                  fontSize="xs"
                />
              }
            />
            <MenuList fontSize="sm">
              <MenuItem isDisabled>
                <Text fontSize="xs" color="gray.500">{user.email || 'usuario'}</Text>
              </MenuItem>
              <MenuItem onClick={handleLogout} color="red.500">
                Sair
              </MenuItem>
            </MenuList>
          </Menu>
        </HStack>
      </Flex>

      <Box as="main" maxW="7xl" mx="auto" px={6} py={6}>
        <Outlet />
      </Box>
    </Box>
  );
}

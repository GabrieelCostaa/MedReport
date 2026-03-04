import { extendTheme } from '@chakra-ui/react';

const theme = extendTheme({
  colors: {
    brand: {
      50: '#e6f4f0',
      100: '#b3dfce',
      200: '#80caac',
      300: '#4db58a',
      500: '#1a9f68',
      600: '#157f53',
      700: '#105f3e',
      800: '#0a402a',
      900: '#052015',
    },
  },
  fonts: {
    heading: 'var(--font-heading), system-ui, sans-serif',
    body: 'var(--font-body), system-ui, sans-serif',
  },
});

export default theme;

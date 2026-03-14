import { extendTheme } from '@chakra-ui/react';

const theme = extendTheme({
  config: {
    initialColorMode: 'light',
    useSystemColorMode: false,
  },
  colors: {
    brand: {
      50: '#f0f9f7',
      100: '#d0ede8',
      200: '#a3dbd1',
      300: '#6ec4b5',
      400: '#3ba899',
      500: '#0d9488',
      600: '#0b7e74',
      700: '#0f766e',
      800: '#115e59',
      900: '#134e4a',
    },
    medical: {
      50: '#f0f7ff',
      100: '#dbeafe',
      200: '#bfdbfe',
      500: '#1B4D6E',
      600: '#164060',
      700: '#0f3350',
      800: '#0a2540',
      900: '#061b2e',
    },
  },
  fonts: {
    heading: "'Inter', system-ui, -apple-system, sans-serif",
    body: "'Inter', system-ui, -apple-system, sans-serif",
  },
  styles: {
    global: {
      body: {
        bg: '#f8fafc',
        color: '#1a202c',
      },
    },
  },
  components: {
    Button: {
      defaultProps: {
        colorScheme: 'brand',
      },
    },
    Input: {
      defaultProps: {
        focusBorderColor: 'brand.500',
      },
    },
    Textarea: {
      defaultProps: {
        focusBorderColor: 'brand.500',
      },
    },
    Select: {
      defaultProps: {
        focusBorderColor: 'brand.500',
      },
    },
  },
});

export default theme;

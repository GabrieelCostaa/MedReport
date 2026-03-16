import { extendTheme, type ThemeConfig } from '@chakra-ui/react';

const config: ThemeConfig = {
  initialColorMode: 'light',
  useSystemColorMode: false,
};

const theme = extendTheme({
  config,
  colors: {
    brand: {
      50: '#f8fce8',
      100: '#eef7c4',
      200: '#ddef8e',
      300: '#c8e64e',
      400: '#b5d43a',
      500: '#a3c23a',
      600: '#8fa83a',
      700: '#6e8230',
      800: '#556526',
      900: '#3d4a1c',
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
  semanticTokens: {
    colors: {
      'surface': { default: 'white', _dark: 'gray.800' },
      'surface.subtle': { default: 'gray.50', _dark: 'gray.700' },
      'surface.muted': { default: '#f8fafc', _dark: 'gray.900' },
      'border.subtle': { default: 'gray.100', _dark: 'gray.700' },
      'border.muted': { default: 'gray.200', _dark: 'gray.600' },
      'text.primary': { default: 'gray.800', _dark: 'whiteAlpha.900' },
      'text.secondary': { default: 'gray.600', _dark: 'gray.300' },
      'text.muted': { default: 'gray.500', _dark: 'gray.400' },
      'text.subtle': { default: 'gray.400', _dark: 'gray.500' },
      'brand.surface': { default: 'brand.50', _dark: 'brand.900' },
      'brand.border': { default: 'brand.100', _dark: 'brand.800' },
      'brand.text': { default: 'brand.700', _dark: 'brand.300' },
    },
  },
  fonts: {
    heading: "'Inter', system-ui, -apple-system, sans-serif",
    body: "'Inter', system-ui, -apple-system, sans-serif",
  },
  styles: {
    global: (props: { colorMode: string }) => ({
      body: {
        bg: props.colorMode === 'dark' ? 'gray.900' : '#f8fafc',
        color: props.colorMode === 'dark' ? 'whiteAlpha.900' : 'gray.800',
      },
    }),
  },
  components: {
    Button: {
      defaultProps: {
        colorScheme: 'brand',
      },
      variants: {
        solid: (props: { colorScheme: string }) => {
          if (props.colorScheme === 'brand') {
            return {
              bg: 'brand.300',
              color: 'gray.900',
              _hover: { bg: 'brand.200', _disabled: { bg: 'brand.300' } },
              _active: { bg: 'brand.400' },
            };
          }
          return {};
        },
        outline: (props: { colorScheme: string }) => {
          if (props.colorScheme === 'brand') {
            return {
              borderColor: 'brand.300',
              color: 'brand.text',
              _hover: { bg: 'brand.surface' },
            };
          }
          return {};
        },
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

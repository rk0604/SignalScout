import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css'; // design tokens (see docs/ROADMAP.md)
import RootApp from './RootApp';

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error("Root element not found");
}

createRoot(rootElement).render(
  <StrictMode>
    <RootApp />
  </StrictMode>
);


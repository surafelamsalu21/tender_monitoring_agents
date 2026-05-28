import React from 'react';
import { render, screen } from '@testing-library/react';
import { LoginPage } from './components/LoginPage';

jest.mock('./services/api', () => ({
  apiService: { login: jest.fn() },
  setAuthToken: jest.fn(),
}));

test('renders Precise branding on login', () => {
  render(<LoginPage onLoginSuccess={() => {}} />);
  expect(screen.getByText(/^Precise$/i)).toBeInTheDocument();
  expect(screen.getByText(/Growth Accelerated/i)).toBeInTheDocument();
});

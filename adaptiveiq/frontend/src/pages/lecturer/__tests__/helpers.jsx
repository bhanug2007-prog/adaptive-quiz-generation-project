import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '../../../components/ui'

export function renderAt(ui, { path = '/', route = '/' } = {}) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[route]}>
        <Routes><Route path={path} element={ui} /></Routes>
      </MemoryRouter>
    </ToastProvider>,
  )
}

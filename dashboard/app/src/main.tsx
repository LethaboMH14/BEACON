/**
 * Two surfaces, one build.
 *
 *   /            member app — the phone product (MemberShell + member/screens/*)
 *   /ops         operations console — the existing five screens (App.tsx)
 *
 * Until now App.tsx was a useState tab switcher, not a router, so there were no
 * URLs to link between. The member app needs real navigation (the assistant
 * cites a suburb and sends you to the map; home links to route planning) and a
 * demo needs deep-linkable screens, so routing is now real. App.tsx keeps its
 * own internal tab state for the ops screens — that switcher works, and
 * rewriting it would be churn rather than improvement.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import '@fontsource-variable/inter'
import './index.css'
import App from './App.tsx'
import MemberShell from './member/MemberShell.tsx'
import Home from './member/screens/Home.tsx'
import LiveDrive from './member/screens/LiveDrive.tsx'
import VisionLens from './member/screens/VisionLens.tsx'
import HotspotMap from './member/screens/HotspotMap.tsx'
import SafestRoute from './member/screens/SafestRoute.tsx'
import HomeGuard from './member/screens/HomeGuard.tsx'
import HomeGuardDemo from './member/screens/HomeGuardDemo.tsx'
import Assistant from './member/screens/Assistant.tsx'
import Rewards from './member/screens/Rewards.tsx'
import { LogProvider } from './member/LogContext.tsx'

const router = createBrowserRouter([
  {
    path: '/',
    element: <MemberShell />,
    children: [
      { index: true, element: <Navigate to="/home" replace /> },
      { path: 'home', element: <Home /> },
      { path: 'drive', element: <LiveDrive /> },
      { path: 'vision', element: <VisionLens /> },
      { path: 'map', element: <HotspotMap /> },
      { path: 'route', element: <SafestRoute /> },
      { path: 'home-guard', element: <LogProvider><HomeGuard /></LogProvider> },
      { path: 'assistant', element: <Assistant /> },
      { path: 'rewards', element: <Rewards /> },
    ],
  },
  { path: '/ops', element: <App /> },
  { path: '/demo', element: <HomeGuardDemo /> },
  // Anything unknown lands on the member app rather than a blank screen — a 404
  // in front of a judge is worse than a redirect.
  { path: '*', element: <Navigate to="/home" replace /> },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)

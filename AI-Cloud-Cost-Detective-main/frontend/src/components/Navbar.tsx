import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'
import { BarChart3, History, KeyRound, LogOut, Sun, Moon } from 'lucide-react'
import LinkedInBadge from './LinkedInBadge'

export default function Navbar() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate  = useNavigate()
  const location  = useLocation()

  const handleLogout = () => { logout(); navigate('/login') }

  const isActive = (path: string) => location.pathname === path

  return (
    <nav className="app-banner sticky top-0 z-50" style={{ boxShadow: '0 4px 24px rgba(0,0,0,0.55)' }}>
      {/* Ambient orbs */}
      <div style={{ position: 'absolute', inset: 0, zIndex: 0, overflow: 'hidden', pointerEvents: 'none' }}>
        <div style={{
          position: 'absolute', width: '300px', height: '300px', borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(42,82,152,0.22) 0%, transparent 70%)',
          top: '-140px', left: '-50px',
        }} />
        <div style={{
          position: 'absolute', width: '220px', height: '220px', borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(201,146,42,0.1) 0%, transparent 70%)',
          top: '-90px', right: '-30px',
        }} />
      </div>

      {/* Main row */}
      <div className="max-w-7xl mx-auto px-4 h-[64px] flex items-center gap-4"
        style={{ position: 'relative', zIndex: 2 }}>

        {/* Logo */}
        <Link to="/" className="flex items-center gap-3 shrink-0 no-underline">
          <div className="app-logo-badge">AI</div>
          <div style={{
            width: '1px', alignSelf: 'stretch', margin: '14px 0', flexShrink: 0,
            background: 'linear-gradient(180deg, transparent, rgba(240,200,74,0.45), transparent)',
          }} />
          <div>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: '0.88em', letterSpacing: '0.3px', lineHeight: 1.3 }}>
              Cloud Cost Detective
            </div>
            <div className="hidden sm:flex items-center gap-1.5 mt-0.5">
              {[
                { label: 'AWS',   bg: '#FF9900' },
                { label: 'Azure', bg: '#0078D4' },
                { label: 'GCP',   bg: '#4285F4' },
              ].map(({ label, bg }) => (
                <span key={label} style={{
                  background: bg, borderRadius: '4px',
                  padding: '1px 5px', fontSize: '0.58rem', fontWeight: 800,
                  color: '#fff', letterSpacing: '0.8px',
                }}>{label}</span>
              ))}
              <span style={{ color: 'rgba(255,255,255,0.28)', fontSize: '0.58rem', letterSpacing: '0.4px' }}>
                Multi-Cloud Intelligence
              </span>
            </div>
          </div>
        </Link>

        {/* Nav links — center */}
        <div className="flex items-center gap-1 mx-auto">
          {[
            { to: '/',        Icon: BarChart3, label: 'Dashboard' },
            { to: '/history', Icon: History,   label: 'History'   },
          ].map(({ to, Icon, label }) => (
            <Link key={to} to={to}
              className={`nav-link flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all${isActive(to) ? ' nav-link--active' : ''}`}
            >
              <Icon size={14} />
              <span className="hidden sm:inline">{label}</span>
            </Link>
          ))}
        </div>

        {/* Right controls */}
        <div className="flex items-center gap-2 shrink-0">
          {user?.email && (
            <span className="hidden md:block truncate max-w-[180px]"
              style={{ color: 'rgba(255,255,255,0.45)', fontSize: '0.78em' }}>
              {user.email}
            </span>
          )}

          <LinkedInBadge className="hidden lg:inline-flex" />

          {/* Theme toggle */}
          <button onClick={toggleTheme} className="btn-theme-toggle"
            title={theme === 'dark' ? 'Light mode' : 'Dark mode'}>
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          <Link to="/change-password"
            className="btn-ghost flex items-center gap-1.5 text-sm"
            style={{
              color: isActive('/change-password') ? '#fff' : undefined,
              background: isActive('/change-password') ? 'rgba(255,255,255,0.13)' : undefined,
            }}>
            <KeyRound size={14} />
            <span className="hidden sm:block">Password</span>
          </Link>

          <button onClick={handleLogout} className="btn-ghost flex items-center gap-1.5 text-sm">
            <LogOut size={14} />
            <span className="hidden sm:block">Logout</span>
          </button>
        </div>
      </div>

      {/* Gold accent stripe */}
      <div className="banner-stripe" />
    </nav>
  )
}

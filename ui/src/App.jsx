import React, { useState, useCallback, useEffect } from "react";
import axios from "axios";
axios.defaults.withCredentials = true;
axios.interceptors.request.use((config) => {
  const accessToken = localStorage.getItem("accessToken");
  if (accessToken) {
    config.headers["Authorization"] = `Bearer ${accessToken}`;
  }
  if (["post", "put", "patch", "delete"].includes(config.method?.toLowerCase())) {
    const csrfToken = sessionStorage.getItem("csrfToken");
    if (csrfToken) config.headers["X-CSRF-Token"] = csrfToken;
  }
  return config;
});
import LightRays from "./LightRays";
import {
  UploadCloud,
  FileText,
  Search,
  Database,
  Trash2,
  AlertCircle,
  CheckCircle,
  Loader2,
  BookOpen,
  File,
  Info,
  Moon,
  Sun,
  LogOut,
  User,
  Mail,
  Eye,
  EyeOff
} from "lucide-react";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");

// Minimalist Semantic Colors for plagiarism matches
const SOURCE_COLORS = [
  {
    text: "text-zinc-900 dark:text-zinc-100",
    bg: "bg-zinc-100 dark:bg-zinc-800",
    highlight: "bg-zinc-200 dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 rounded-sm px-0.5",
    dot: "bg-zinc-900 dark:bg-zinc-100 text-white dark:text-black",
  },
  {
    text: "text-neutral-700 dark:text-neutral-300",
    bg: "bg-neutral-100 dark:bg-neutral-800",
    highlight: "bg-neutral-200 dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 rounded-sm px-0.5",
    dot: "bg-neutral-700 dark:bg-neutral-300 text-white dark:text-black",
  },
  {
    text: "text-stone-700 dark:text-stone-300",
    bg: "bg-stone-100 dark:bg-stone-800",
    highlight: "bg-stone-200 dark:bg-stone-700 text-stone-900 dark:text-stone-100 rounded-sm px-0.5",
    dot: "bg-stone-700 dark:bg-stone-300 text-white dark:text-black",
  }
];

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(localStorage.getItem("isAuthenticated") === "true");
  const [email, setEmail] = useState(localStorage.getItem("email"));
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem("isDarkMode");
    if (saved !== null) return saved === "true";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    localStorage.setItem("isDarkMode", isDarkMode);
  }, [isDarkMode]);

  const handleLogin = (newEmail, csrfToken, accessToken) => {
    localStorage.setItem("isAuthenticated", "true");
    localStorage.setItem("email", newEmail);
    if (accessToken) localStorage.setItem("accessToken", accessToken);
    if (csrfToken) sessionStorage.setItem("csrfToken", csrfToken);
    setIsAuthenticated(true);
    setEmail(newEmail);
  };

  const handleLogout = async () => {
    try {
      await axios.post(`${API_BASE}/logout`);
    } catch (e) {
      console.error("Logout failed", e);
    }
    localStorage.removeItem("isAuthenticated");
    localStorage.removeItem("email");
    localStorage.removeItem("accessToken");
    sessionStorage.removeItem("csrfToken");
    setIsAuthenticated(false);
    setEmail(null);
  };

  useEffect(() => {
    if (!isAuthenticated || sessionStorage.getItem("csrfToken")) return;
    axios.get(`${API_BASE}/csrf-token`)
      .then((res) => sessionStorage.setItem("csrfToken", res.data.csrf_token))
      .catch((err) => {
        if (err.response?.status === 401 && !localStorage.getItem("accessToken")) {
          handleLogout();
        }
      });
  }, [isAuthenticated]);

  return (
    <div className={isDarkMode ? "dark" : ""}>
      <div className="h-screen flex flex-col font-sans bg-white dark:bg-[#0a0a0a] text-zinc-900 dark:text-zinc-100 transition-colors duration-500 relative">
        {!isAuthenticated ? (
          <AuthScreen onLogin={handleLogin} isDarkMode={isDarkMode} setIsDarkMode={setIsDarkMode} />
        ) : (
          <PlagiarismDashboard 
            email={email} 
            onLogout={handleLogout} 
            isDarkMode={isDarkMode} 
            setIsDarkMode={setIsDarkMode} 
          />
        )}
      </div>
    </div>
  );
}

function AuthScreen({ onLogin, isDarkMode, setIsDarkMode }) {
  const [authMode, setAuthMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccessMsg("");
    setLoading(true);

    try {
      if (authMode === "register") {
        const res = await axios.post(`${API_BASE}/register`, { email, password });
        setSuccessMsg(res.data.message);
        setAuthMode("login");
        setPassword("");
      } else if (authMode === "login") {
        const res = await axios.post(`${API_BASE}/login`, { email, password });
        onLogin(res.data.email, res.data.csrf_token, res.data.access_token);
      }
    } catch (err) {
      if (err.response?.status === 429) {
        setError("Too many requests. Please wait a minute and try again.");
      } else if (!err.response) {
        setError("Unable to connect to backend server. Please verify backend URL and deployment status.");
      } else {
        let detail = err.response?.data?.detail;
        if (Array.isArray(detail)) {
          detail = detail.map((d) => (typeof d === "object" ? d.msg || JSON.stringify(d) : String(d))).join(", ");
        } else if (typeof detail === "object" && detail !== null) {
          detail = detail.msg || JSON.stringify(detail);
        }
        setError(typeof detail === "string" && detail ? detail : "Authentication failed");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center p-4 animate-fade-in relative overflow-hidden">
      <div className="absolute inset-0 z-0">
        <LightRays
          raysOrigin="top-center"
          raysColor={isDarkMode ? "#ffffff" : "#27272a"}
          raysSpeed={1.5}
          lightSpread={0.8}
          rayLength={1.2}
          followMouse={true}
          mouseInfluence={0.1}
          noiseAmount={0.1}
          distortion={0.05}
          className="custom-rays opacity-50 dark:opacity-70"
        />
      </div>

      <button 
        onClick={() => setIsDarkMode(!isDarkMode)}
        className="absolute top-6 right-6 p-2 rounded-full bg-white/50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors z-20 backdrop-blur-sm"
      >
        {isDarkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
      </button>

      <div className="w-full max-w-[400px] animate-slide-up relative z-10">
        <div className="flex items-center justify-center gap-2 mb-10 text-zinc-900 dark:text-zinc-100">
          <BookOpen className="w-8 h-8" />
          <h1 className="font-bold text-3xl tracking-tighter">CheckMate</h1>
        </div>
        
        <div className="bg-white/80 dark:bg-[#0a0a0a]/80 backdrop-blur-xl p-10 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-2xl shadow-zinc-200/50 dark:shadow-none transition-colors">
          <h2 className="text-center font-medium text-lg mb-8 tracking-tight text-zinc-600 dark:text-zinc-400">
            {authMode === "register" ? "Create an account" : "Log in to your account"}
          </h2>
          
          {error && (
            <div className="bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm mb-6 flex items-center gap-2 border border-red-100 dark:border-red-900/50 animate-fade-in">
              <AlertCircle className="w-4 h-4 shrink-0" /> {error}
            </div>
          )}

          {successMsg && (
            <div className="bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400 p-3 rounded-lg text-sm mb-6 flex items-center gap-2 border border-emerald-100 dark:border-emerald-900/50 animate-fade-in">
              <CheckCircle className="w-4 h-4 shrink-0" /> {successMsg}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-2">Email address</label>
                <div className="relative">
                  <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
                  <input 
                    type="email" 
                    required
                    className="w-full border border-zinc-200 dark:border-zinc-800 bg-transparent rounded-lg pl-10 pr-3 py-2.5 text-sm focus:ring-1 focus:ring-zinc-900 dark:focus:ring-zinc-100 focus:border-zinc-900 dark:focus:border-zinc-100 outline-none transition-all placeholder:text-zinc-400"
                    placeholder="name@example.com"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-2">
                  Password
                </label>
                <div className="relative">
                  <input 
                    type={showPassword ? "text" : "password"}
                    required
                    minLength={6}
                    className="w-full border border-zinc-200 dark:border-zinc-800 bg-transparent rounded-lg pl-3 pr-10 py-2.5 text-sm focus:ring-1 focus:ring-zinc-900 dark:focus:ring-zinc-100 focus:border-zinc-900 dark:focus:border-zinc-100 outline-none transition-all"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition-colors"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            
            <button 
              type="submit" 
              disabled={loading}
              className="w-full bg-zinc-900 dark:bg-zinc-100 hover:bg-zinc-800 dark:hover:bg-white text-white dark:text-zinc-900 py-2.5 rounded-lg text-sm font-medium transition-all active:scale-[0.98] flex justify-center items-center gap-2 disabled:opacity-70 disabled:active:scale-100 mt-2"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {authMode === "register" ? "Create Account" : "Log In"}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-zinc-100 dark:border-zinc-800 text-center text-xs text-zinc-500">
            {authMode === "register" ? "Already have an account?" : "Don't have an account?"}
            <button 
              type="button"
              onClick={() => {
                setAuthMode(authMode === "register" ? "login" : "register");
                setError("");
                setSuccessMsg("");
              }}
              className="ml-2 font-medium text-zinc-900 dark:text-zinc-100 hover:underline"
            >
              {authMode === "register" ? "Log in" : "Sign up"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function PlagiarismDashboard({ email, onLogout, isDarkMode, setIsDarkMode }) {
  const [viewMode, setViewMode] = useState("analyzer");
  const [file, setFile] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedSegment, setSelectedSegment] = useState(null);

  const [dbFiles, setDbFiles] = useState([]);
  const [arxivTopic, setArxivTopic] = useState("");
  const [arxivResults, setArxivResults] = useState([]);
  const [arxivLoading, setArxivLoading] = useState(false);

  const fetchDbFiles = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/database/files`);
      setDbFiles(res.data.files);
    } catch (err) {
      if (err.response?.status === 401) onLogout();
      console.error(err);
    }
  }, [onLogout]);

  useEffect(() => {
    if (viewMode === "database") fetchDbFiles();
  }, [viewMode, fetchDbFiles]);

  const handleAnalyze = async () => {
    if (!file) return;
    setLoading(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await axios.post(`${API_BASE}/analyze`, formData);
      setAnalysis(response.data);
    } catch (err) {
      if (err.response?.status === 401) onLogout();
    } finally {
      setLoading(false);
    }
  };

  const handleArxivSearch = async () => {
    if (!arxivTopic.trim()) return;
    setArxivLoading(true);
    try {
      const res = await axios.get(
        `${API_BASE}/arxiv/search?topic=${encodeURIComponent(arxivTopic)}`
      );
      setArxivResults(res.data.results);
    } catch(err) {
      if (err.response?.status === 401) onLogout();
    } finally {
      setArxivLoading(false);
    }
  };

  const indexArxivPaper = async (paper) => {
    try {
      await axios.post(`${API_BASE}/arxiv/download`, {
        pdf_url: paper.pdf_url,
        title: paper.title,
      });
      fetchDbFiles();
    } catch (err) {
      if (err.response?.status === 401) onLogout();
    }
  };

  const deleteDbFile = async (filename) => {
    try {
      await axios.delete(`${API_BASE}/database/files/${filename}`);
      fetchDbFiles();
    } catch(err) {
      if (err.response?.status === 401) onLogout();
    }
  };

  const getSourceColor = (sourceName) => {
    if (!analysis || !sourceName) return null;
    const index = analysis.sources.findIndex((s) => s.filename === sourceName);
    return SOURCE_COLORS[index % SOURCE_COLORS.length];
  };

  const renderHighlightedText = (segment) => {
    if (segment.status === "ORIGINAL" || !segment.matched_words) {
      return <span className="text-zinc-600 dark:text-zinc-400">{segment.text} </span>;
    }

    const color = getSourceColor(segment.source);
    const words = segment.text.split(" ");

    return (
      <span
        className={`cursor-pointer transition-all duration-300 ease-out ${
          selectedSegment === segment
            ? "ring-2 ring-zinc-300 dark:ring-zinc-600 bg-zinc-50 dark:bg-zinc-800/50 rounded"
            : "hover:bg-zinc-50 dark:hover:bg-zinc-900/50"
        }`}
        onClick={() => setSelectedSegment(segment)}
      >
        {words.map((w, i) => {
          const cleanWord = w.replace(/[.,!?()]/g, "").toLowerCase();
          const isMatch = segment.matched_words.includes(cleanWord);
          if (isMatch) {
            return (
              <mark
                key={i}
                className={`bg-transparent transition-colors ${color.highlight}`}
              >
                {w}
              </mark>
            );
          }
          return <span key={i} className="text-zinc-900 dark:text-zinc-100"> {w} </span>;
        })}
      </span>
    );
  };

  return (
    <>
      <header className="bg-white/80 dark:bg-[#0a0a0a]/80 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-900 h-16 flex items-center px-8 gap-8 shrink-0 z-20 shadow-sm">
        <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
          <BookOpen className="w-5 h-5" />
          <h1 className="font-bold text-lg tracking-tight">CheckMate</h1>
        </div>

        <nav className="flex gap-2 ml-8 flex-1">
          <button
            onClick={() => setViewMode("analyzer")}
            className={`px-3 py-1.5 rounded-md text-sm transition-all duration-300 ${
              viewMode === "analyzer"
                ? "bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 font-medium"
                : "text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300"
            }`}
          >
            Analyzer
          </button>
          <button
            onClick={() => setViewMode("database")}
            className={`px-3 py-1.5 rounded-md text-sm transition-all duration-300 ${
              viewMode === "database"
                ? "bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 font-medium"
                : "text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300"
            }`}
          >
            Database
          </button>
        </nav>
        
        <div className="flex items-center gap-6">
          <button
            onClick={() => setIsDarkMode(!isDarkMode)}
            className="text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
          >
            {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-500">{email}</span>
            <button
              onClick={onLogout}
              className="text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden relative">
        {viewMode === "database" ? (
          <div className="flex-1 p-8 lg:p-12 overflow-y-auto bg-zinc-50 dark:bg-[#0a0a0a] animate-fade-in">
            <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12">
              <div className="animate-slide-up bg-white dark:bg-zinc-900/40 p-8 rounded-3xl border border-zinc-200 dark:border-zinc-800 shadow-xl shadow-zinc-200/40 dark:shadow-none" style={{animationDelay: "0.1s"}}>
                <div className="mb-8">
                  <h2 className="font-semibold text-xl flex items-center gap-2">
                    Indexed Sources
                  </h2>
                  <p className="text-sm text-zinc-500 mt-1">
                    Your private vector database.
                  </p>
                </div>
                <div className="space-y-3">
                  {dbFiles.length === 0 ? (
                    <div className="text-center py-12 text-zinc-400 border border-dashed border-zinc-300 dark:border-zinc-700 rounded-2xl bg-zinc-50/50 dark:bg-zinc-900/50">
                      <File className="w-8 h-8 mx-auto mb-3 opacity-50" />
                      <p className="text-sm">No sources yet.</p>
                    </div>
                  ) : (
                    dbFiles.map((f, i) => (
                      <div
                        key={i}
                        className="flex justify-between items-center p-4 rounded-xl border border-zinc-100 dark:border-zinc-800 bg-white dark:bg-[#111] hover:border-zinc-300 dark:hover:border-zinc-700 transition-all group"
                      >
                        <div className="flex items-center gap-3 overflow-hidden">
                          <FileText className="w-4 h-4 text-zinc-400 shrink-0" />
                          <span className="text-sm font-medium truncate">{f}</span>
                        </div>
                        <button
                          onClick={() => deleteDbFile(f)}
                          className="opacity-0 group-hover:opacity-100 p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-all text-zinc-500 hover:text-red-500"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="animate-slide-up bg-white dark:bg-zinc-900/40 p-8 rounded-3xl border border-zinc-200 dark:border-zinc-800 shadow-xl shadow-zinc-200/40 dark:shadow-none flex flex-col" style={{animationDelay: "0.2s"}}>
                <div className="mb-8">
                  <h2 className="font-semibold text-xl flex items-center gap-2">
                    Import from ArXiv
                  </h2>
                  <p className="text-sm text-zinc-500 mt-1">
                    Index academic papers directly.
                  </p>
                </div>
                <div className="flex gap-3 mb-8">
                  <div className="relative flex-1">
                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
                    <input
                      className="w-full bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 py-2.5 pl-9 pr-4 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-100 transition-all"
                      placeholder="Search research topics..."
                      value={arxivTopic}
                      onChange={(e) => setArxivTopic(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleArxivSearch()}
                    />
                  </div>
                  <button
                    onClick={handleArxivSearch}
                    disabled={arxivLoading}
                    className="bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-6 rounded-xl text-sm font-medium transition-all active:scale-[0.98] disabled:opacity-50 shadow-md"
                  >
                    {arxivLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Search"}
                  </button>
                </div>
                <div className="space-y-4">
                  {arxivResults.map((res, i) => (
                    <div
                      key={i}
                      className="p-5 rounded-xl border border-zinc-100 dark:border-zinc-800 bg-white dark:bg-[#111] hover:border-zinc-300 dark:hover:border-zinc-700 transition-all"
                    >
                      <h3 className="text-sm font-semibold mb-2 leading-snug">{res.title}</h3>
                      <p className="text-xs text-zinc-500 line-clamp-2 mb-4">{res.summary}</p>
                      <button
                        onClick={() => indexArxivPaper(res)}
                        className="text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors flex items-center gap-1.5"
                      >
                        <UploadCloud className="w-3.5 h-3.5" /> Index Paper
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto bg-zinc-50 dark:bg-[#0a0a0a] flex flex-col items-center p-8 lg:p-12 transition-colors relative">
              {!analysis ? (
                <div className="m-auto w-full max-w-md animate-slide-up">
                  <div className="bg-white dark:bg-zinc-900/40 p-12 rounded-[2rem] border border-zinc-200 dark:border-zinc-800 shadow-2xl shadow-zinc-200/50 dark:shadow-none text-center">
                    <div className="w-16 h-16 border border-zinc-200 dark:border-zinc-800 rounded-2xl flex items-center justify-center mx-auto mb-6 bg-zinc-50 dark:bg-zinc-800 shadow-sm">
                      <UploadCloud className="w-6 h-6 text-zinc-600 dark:text-zinc-300" />
                    </div>
                    <h3 className="text-2xl font-bold mb-3 tracking-tight">Upload Document</h3>
                    <p className="text-zinc-500 text-sm mb-10 leading-relaxed px-4">
                      Select a text or PDF file to scan for similarity against your personal vector database.
                    </p>
                    <input
                      type="file"
                      id="file-upload"
                      className="hidden"
                      onChange={(e) => setFile(e.target.files[0])}
                    />
                    <label
                      htmlFor="file-upload"
                      className="cursor-pointer flex flex-col items-center justify-center w-full border-2 border-dashed border-zinc-300 dark:border-zinc-700 rounded-2xl p-10 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 hover:border-zinc-400 dark:hover:border-zinc-500 transition-all mb-6 group"
                    >
                      <span className="text-sm font-semibold text-zinc-600 dark:text-zinc-400 group-hover:text-zinc-900 dark:group-hover:text-zinc-200 transition-colors">
                        {file ? file.name : "Browse files"}
                      </span>
                    </label>
                    <button
                      onClick={handleAnalyze}
                      disabled={!file || loading}
                      className="w-full bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 py-3.5 rounded-xl text-sm font-semibold transition-all active:scale-[0.98] disabled:opacity-50 flex items-center justify-center gap-2 shadow-lg shadow-zinc-900/20 dark:shadow-none"
                    >
                      {loading ? <><Loader2 className="w-5 h-5 animate-spin" /> Scanning...</> : "Scan Document"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="bg-white dark:bg-[#111] border border-zinc-100 dark:border-zinc-900 w-full max-w-3xl p-10 lg:p-16 font-serif leading-loose text-lg text-justify rounded-2xl min-h-full animate-fade-in shadow-sm">
                  {analysis.segments.map((seg, i) => (
                    <React.Fragment key={i}>{renderHighlightedText(seg)}</React.Fragment>
                  ))}
                </div>
              )}
            </div>

            {analysis && (
              <div className="w-[360px] bg-white dark:bg-[#111] border-l border-zinc-100 dark:border-zinc-900 flex flex-col shrink-0 z-10 animate-slide-in-right shadow-2xl lg:shadow-none">
                <div className="p-8 border-b border-zinc-100 dark:border-zinc-900 flex flex-col items-center justify-center bg-zinc-50/50 dark:bg-transparent">
                  <div className="w-24 h-24 rounded-full border-[6px] border-zinc-100 dark:border-zinc-800 flex flex-col items-center justify-center mb-4">
                    <span className="text-3xl font-bold tracking-tighter">
                      {analysis.summary.plagiarism_percent}%
                    </span>
                  </div>
                  <span className="block text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                    Similarity Score
                  </span>
                </div>

                <div className="flex-1 overflow-y-auto p-6">
                  <h3 className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-6">Match Overview</h3>
                  <div className="space-y-3">
                    {analysis.sources.map((src, i) => {
                      const color = SOURCE_COLORS[i % SOURCE_COLORS.length];
                      return (
                        <div key={i} className="flex items-center gap-3 p-3 border border-zinc-100 dark:border-zinc-800 rounded-xl hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors cursor-pointer">
                          <div className={`w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold ${color.dot}`}>
                            {i + 1}
                          </div>
                          <div className="flex-1 truncate text-sm font-medium">{src.filename}</div>
                          <div className="text-xs text-zinc-500">{src.matched_words} w</div>
                        </div>
                      );
                    })}
                  </div>

                  {selectedSegment && selectedSegment.source ? (
                    <div className="mt-8 border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl p-5 animate-slide-up" style={{animationDuration: '0.3s'}}>
                      <div className="flex items-center gap-2 mb-3">
                        <Info className="w-3.5 h-3.5 text-zinc-400" />
                        <h4 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Source Context</h4>
                      </div>
                      <p className="text-sm font-serif italic text-zinc-600 dark:text-zinc-400 leading-relaxed">
                        "...{selectedSegment.matched_db_text}..."
                      </p>
                    </div>
                  ) : (
                    <div className="mt-8 text-center text-sm text-zinc-400 italic px-4">
                      Click highlighted text to view original context.
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}

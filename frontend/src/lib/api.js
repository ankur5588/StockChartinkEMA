import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;
const TOKEN_KEY = "chartink_session_token";

export function setSessionToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}
export function getSessionToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function clearSessionToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

// Attach Authorization: Bearer header from localStorage as a fallback
// for browsers that block httpOnly cross-site cookies (Brave, Safari ITP,
// Firefox strict, mobile browsers, incognito). The backend accepts EITHER
// the cookie OR the bearer header.
api.interceptors.request.use((config) => {
  const token = getSessionToken();
  if (token && !config.headers?.Authorization) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401, drop the local token so the UI cleanly redirects to login
api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error?.response?.status === 401) {
      clearSessionToken();
    }
    return Promise.reject(error);
  }
);

export function isUnauthorized(error) {
  return error?.response?.status === 401;
}

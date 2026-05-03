import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

// Graceful 401 handler - we let each consumer decide but also expose helper.
export function isUnauthorized(error) {
  return error?.response?.status === 401;
}

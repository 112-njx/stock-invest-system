import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.response.use(
  (res) => res.data,
  (err) => {
    console.error('[API Error]', err.config?.url, err.message);
    return Promise.reject(err);
  },
);

export default apiClient;

import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({plugins:[react()],server:{host:'127.0.0.1',port:5278,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:5277',timeout:600000}}},build:{outDir:'/tmp/aria-cnotta-dist',emptyOutDir:false,rollupOptions:{input:'cnotta.html'}}})

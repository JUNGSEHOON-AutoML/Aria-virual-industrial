import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({plugins:[react()],server:{host:'127.0.0.1',port:Number(process.env.CNOTTA_WEB_PORT||5278),strictPort:true,proxy:{'/api':{target:`http://127.0.0.1:${process.env.CNOTTA_API_PORT||5277}`,timeout:600000}}},build:{outDir:'/tmp/aria-cnotta-dist',emptyOutDir:false,rollupOptions:{input:{cnotta:'cnotta.html',overview:'overview.html'}}}})

import '@fontsource-variable/inter'
import '@fontsource/jetbrains-mono/400.css'
import 'vuetify/styles'
import '@cimh/web-app/styles/base.css'
import { boot } from '@cimh/web-app'
import { routes } from 'vue-router/auto-routes'
import App from './App.vue'

boot({ root: App, routes, app: 'shop', appName: 'CIMH Stores', home: '/' })

const ChatBoxRoutes = {
    path: '/chatbox',
    component: () => import('@/layouts/blank/BlankLayout.vue'),
    children: [
      {
        name: 'ChatBox',
        path: '/chatbox',
        component: () => import('@/views/ChatBoxPage.vue')
      }
    ]
  };
  
  export default ChatBoxRoutes;
  
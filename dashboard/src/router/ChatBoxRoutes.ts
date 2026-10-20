const ChatBoxRoutes = {
    path: '/chatbox',
    component: () => import('@/layouts/blank/BlankLayout.vue'),
    children: [
        {
            name: 'ChatBox',
            path: '/chatbox',
            component: () => import('@/views/ChatBoxPage.vue'),
            children: [
                {
                    path: ':conversationId',
                    name: 'ChatBoxDetail',
                    component: () => import('@/views/ChatBoxPage.vue'),
                    props: true
                }
            ]
        }
    ]
};

export default ChatBoxRoutes;

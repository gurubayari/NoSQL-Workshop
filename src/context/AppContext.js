import React, { createContext, useContext, useReducer } from 'react';

export const AppContext = createContext();

const initialState = {
  user: {
    id: 'user-123',
    name: 'John Doe',
    email: 'john.doe@email.com',
    phone: '(555) 123-4567',
    address: '123 Main Street',
    city: 'Seattle',
    state: 'WA',
    zip: '98101'
  },
  cart: [],
  products: [],
  chatMessages: [],
  isAuthenticated: true, // Simulate authenticated user for demo
  isChatOpen: false,
  isTyping: false,
  // Search state
  searchQuery: '',
  searchSuggestions: [],
  searchResults: [],
  isSearching: false,
  searchFilters: {
    category: '',
    priceRange: [0, 1000],
    rating: 0,
    inStock: false
  },
  // UI state
  theme: 'light',
  notifications: [],
  loading: {
    products: false,
    cart: false,
    user: false,
    search: false
  },
  // Reviews state
  reviews: [],
  userReviews: []
};

function appReducer(state, action) {
  switch (action.type) {
    case 'SET_USER':
      return { ...state, user: action.payload, isAuthenticated: !!action.payload };
    
    // Cart actions
    case 'ADD_TO_CART':
      const existingItem = state.cart.find(item => item.id === action.payload.id);
      if (existingItem) {
        return {
          ...state,
          cart: state.cart.map(item =>
            item.id === action.payload.id
              ? { ...item, quantity: item.quantity + 1 }
              : item
          )
        };
      }
      return { ...state, cart: [...state.cart, { ...action.payload, quantity: 1 }] };
    case 'REMOVE_FROM_CART':
      return { ...state, cart: state.cart.filter(item => item.id !== action.payload) };
    case 'UPDATE_CART_QUANTITY':
      return {
        ...state,
        cart: state.cart.map(item =>
          item.id === action.payload.id
            ? { ...item, quantity: action.payload.quantity }
            : item
        )
      };
    case 'CLEAR_CART':
      return { ...state, cart: [] };
    
    // Product actions
    case 'SET_PRODUCTS':
      return { ...state, products: action.payload };
    
    // Chat actions
    case 'TOGGLE_CHAT':
      return { ...state, isChatOpen: !state.isChatOpen };
    case 'ADD_CHAT_MESSAGE':
      return { ...state, chatMessages: [...state.chatMessages, action.payload] };
    case 'SET_TYPING':
      return { ...state, isTyping: action.payload };
    
    // Search actions
    case 'SET_SEARCH_QUERY':
      return { ...state, searchQuery: action.payload };
    case 'SET_SEARCH_SUGGESTIONS':
      return { ...state, searchSuggestions: action.payload };
    case 'SET_SEARCH_RESULTS':
      return { ...state, searchResults: action.payload };
    case 'SET_SEARCHING':
      return { ...state, isSearching: action.payload };
    case 'UPDATE_SEARCH_FILTERS':
      return { ...state, searchFilters: { ...state.searchFilters, ...action.payload } };
    case 'CLEAR_SEARCH':
      return { 
        ...state, 
        searchQuery: '', 
        searchSuggestions: [], 
        searchResults: [], 
        isSearching: false 
      };
    
    // Loading actions
    case 'SET_LOADING':
      return { 
        ...state, 
        loading: { ...state.loading, [action.payload.key]: action.payload.value } 
      };
    
    // Notification actions
    case 'ADD_NOTIFICATION':
      return { 
        ...state, 
        notifications: [...state.notifications, { ...action.payload, id: Date.now() }] 
      };
    case 'REMOVE_NOTIFICATION':
      return { 
        ...state, 
        notifications: state.notifications.filter(n => n.id !== action.payload) 
      };
    
    // Review actions
    case 'SET_REVIEWS':
      return { ...state, reviews: action.payload };
    case 'ADD_REVIEW':
      return { ...state, reviews: [...state.reviews, action.payload] };
    case 'SET_USER_REVIEWS':
      return { ...state, userReviews: action.payload };
    
    // Theme actions
    case 'SET_THEME':
      return { ...state, theme: action.payload };
    
    default:
      return state;
  }
}

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  // Helper functions for easier usage
  
  // Cart functions
  const addToCart = (product) => {
    dispatch({ type: 'ADD_TO_CART', payload: product });
    addNotification({ type: 'success', message: `${product.title} added to cart!` });
  };

  const removeFromCart = (productId) => {
    dispatch({ type: 'REMOVE_FROM_CART', payload: productId });
  };

  const updateCartQuantity = (productId, quantity) => {
    dispatch({ type: 'UPDATE_CART_QUANTITY', payload: { id: productId, quantity } });
  };

  const clearCart = () => {
    dispatch({ type: 'CLEAR_CART' });
  };

  // User functions
  const setUser = (user) => {
    dispatch({ type: 'SET_USER', payload: user });
  };

  // Chat functions
  const toggleChat = () => {
    dispatch({ type: 'TOGGLE_CHAT' });
  };

  const addChatMessage = (message) => {
    dispatch({ type: 'ADD_CHAT_MESSAGE', payload: message });
  };

  // Search functions
  const setSearchQuery = (query) => {
    dispatch({ type: 'SET_SEARCH_QUERY', payload: query });
  };

  const setSearchSuggestions = (suggestions) => {
    dispatch({ type: 'SET_SEARCH_SUGGESTIONS', payload: suggestions });
  };

  const setSearchResults = (results) => {
    dispatch({ type: 'SET_SEARCH_RESULTS', payload: results });
  };

  const setSearching = (isSearching) => {
    dispatch({ type: 'SET_SEARCHING', payload: isSearching });
  };

  const updateSearchFilters = (filters) => {
    dispatch({ type: 'UPDATE_SEARCH_FILTERS', payload: filters });
  };

  const clearSearch = () => {
    dispatch({ type: 'CLEAR_SEARCH' });
  };

  // Loading functions
  const setLoading = (key, value) => {
    dispatch({ type: 'SET_LOADING', payload: { key, value } });
  };

  // Notification functions
  const addNotification = (notification) => {
    dispatch({ type: 'ADD_NOTIFICATION', payload: notification });
    // Auto-remove after 5 seconds
    setTimeout(() => {
      removeNotification(notification.id || Date.now());
    }, 5000);
  };

  const removeNotification = (id) => {
    dispatch({ type: 'REMOVE_NOTIFICATION', payload: id });
  };

  // Review functions
  const setReviews = (reviews) => {
    dispatch({ type: 'SET_REVIEWS', payload: reviews });
  };

  const addReview = (review) => {
    dispatch({ type: 'ADD_REVIEW', payload: review });
    addNotification({ type: 'success', message: 'Review submitted successfully!' });
  };

  const setUserReviews = (reviews) => {
    dispatch({ type: 'SET_USER_REVIEWS', payload: reviews });
  };

  // Theme functions
  const setTheme = (theme) => {
    dispatch({ type: 'SET_THEME', payload: theme });
  };

  const contextValue = {
    // State
    user: state.user,
    cartItems: state.cart,
    products: state.products,
    chatMessages: state.chatMessages,
    isAuthenticated: state.isAuthenticated,
    isChatOpen: state.isChatOpen,
    isTyping: state.isTyping,
    
    // Search state
    searchQuery: state.searchQuery,
    searchSuggestions: state.searchSuggestions,
    searchResults: state.searchResults,
    isSearching: state.isSearching,
    searchFilters: state.searchFilters,
    
    // UI state
    theme: state.theme,
    notifications: state.notifications,
    loading: state.loading,
    
    // Review state
    reviews: state.reviews,
    userReviews: state.userReviews,
    
    // Cart actions
    addToCart,
    removeFromCart,
    updateCartQuantity,
    clearCart,
    
    // User actions
    setUser,
    
    // Chat actions
    toggleChat,
    addChatMessage,
    
    // Search actions
    setSearchQuery,
    setSearchSuggestions,
    setSearchResults,
    setSearching,
    updateSearchFilters,
    clearSearch,
    
    // Loading actions
    setLoading,
    
    // Notification actions
    addNotification,
    removeNotification,
    
    // Review actions
    setReviews,
    addReview,
    setUserReviews,
    
    // Theme actions
    setTheme,
    
    // Raw dispatch for complex actions
    dispatch
  };

  return (
    <AppContext.Provider value={contextValue}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
}
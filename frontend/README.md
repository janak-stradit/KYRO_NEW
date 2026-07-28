# KYRO AML Data Generator - Frontend Dashboard

A modern, orange-themed dashboard interface for the KYRO AML (Anti-Money Laundering) data generator. Built with vanilla HTML, CSS, and JavaScript for maximum performance and simplicity.

## 🎨 Design Features

- **Orange Color Scheme**: Professional orange-themed design with gradients
- **Responsive Layout**: Works on desktop, tablet, and mobile devices
- **Modern UI**: Clean, card-based layout with smooth animations
- **Interactive Dashboard**: Real-time status monitoring and data visualization

## 🚀 Quick Start

### Prerequisites
- Python 3.x (for development server)
- KYRO AML Data Generator backend running on `http://localhost:5050`

### Running the Frontend

1. **Start the development server:**
   ```bash
   cd KYRO_NEW/frontend
   python -m http.server 3000
   ```

2. **Open in browser:**
   ```
   http://localhost:3000
   ```

3. **Ensure backend is running:**
   ```bash
   cd KYRO_NEW
   python app.py
   ```

## 📁 Project Structure

```
frontend/
├── index.html          # Main dashboard page
├── styles/
│   └── main.css       # Orange-themed styles
├── js/
│   └── main.js        # Dashboard functionality
├── package.json       # Project configuration
└── README.md          # This file
```

## 🎯 Dashboard Sections

### 1. Dashboard Overview
- System health status indicator
- Real-time statistics (customers, accounts, transactions)
- Activity log with timestamps
- Quick health check functionality

### 2. Data Generator
- Customer count input (1-10,000 range)
- JSON data generation
- Excel file download with timestamp
- Real-time estimation calculator
- Progress indicators

### 3. Data Preview
- Single customer data preview
- Sample accounts and transactions display
- Interactive customer index selection
- Formatted data tables

## 🎨 Orange Color Palette

The dashboard uses a carefully crafted orange color scheme:

- **Primary Orange**: `#ff6b35` - Main brand color
- **Secondary Orange**: `#ff8c42` - Accent elements
- **Light Orange**: `#ffb366` - Backgrounds and highlights
- **Dark Orange**: `#e55a2b` - Hover states
- **Accent Orange**: `#ffa366` - Icons and decorative elements

## 🔧 Technical Features

### Modern CSS
- CSS Custom Properties (CSS Variables)
- Flexbox and CSS Grid layouts
- Smooth transitions and animations
- Responsive design patterns

### Vanilla JavaScript
- ES6+ class-based architecture
- Async/await for API calls
- Modern DOM manipulation
- Toast notifications system
- Progress tracking

### API Integration
- RESTful API communication
- Error handling and user feedback
- File download functionality
- Real-time data updates

## 📱 Responsive Design

The dashboard is fully responsive with breakpoints for:
- **Desktop**: > 768px (Full layout)
- **Tablet**: 768px - 480px (Adjusted layout)
- **Mobile**: < 480px (Stacked layout)

## 🔗 API Endpoints

The frontend communicates with these backend endpoints:

- `GET /api/health` - System health check
- `GET /api/stats` - Data generation estimates
- `POST /api/generate` - Generate JSON dataset
- `POST /api/generate/download` - Download Excel file
- `POST /api/generate/single-customer` - Generate preview data

## 🎉 Features

### Interactive Elements
- ✅ Navigation between sections
- ✅ Real-time form validation
- ✅ Progress bars and loading states
- ✅ Toast notifications
- ✅ Data tables with formatting

### User Experience
- ✅ Smooth page transitions
- ✅ Hover effects and micro-interactions
- ✅ Clear visual feedback
- ✅ Responsive touch targets
- ✅ Accessibility considerations

## 🛠 Development

### File Organization
- Keep styles modular and well-commented
- Use semantic HTML structure
- Follow consistent naming conventions
- Maintain clean JavaScript architecture

### Customization
- Colors defined in CSS custom properties
- Easy theme modifications
- Scalable component structure
- Clean separation of concerns

## 📊 Integration with Existing Project

This frontend is designed to work seamlessly with the existing KYRO AML data generator while referencing design patterns from the main Digitalworker project structure.

### Connection to Backend
- Connects to Flask API on port 5050
- Handles all CRUD operations
- Provides real-time feedback
- Supports file downloads

### Future Enhancements
- TypeScript migration option
- Component framework integration
- Advanced data visualization
- User authentication
- Custom theme options

---

**Note**: This dashboard maintains the existing generator and test files unchanged while providing a modern, user-friendly interface with the requested orange color scheme.
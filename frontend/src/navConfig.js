import {
  Newspaper,
  Play, Download, RefreshCw, Sparkles, TrendingUp, Search, Globe,
  Layers, Users, Bookmark, Upload, Activity, CalendarDays, Bell,
  Heart, BarChart3, Settings, History, HeartPulse, GitCompare,
} from "lucide-react";

const navItems = [
  { id: "tonight", label: "Watch Tonight", icon: Play, section: "Recommendations" },
  { id: "grab", label: "Worth Grabbing", icon: Download, section: "Recommendations" },
  { id: "rediscover", label: "Rediscover", icon: RefreshCw, section: "Recommendations" },
  { id: "feed", label: "Your Weekly Mix", icon: Newspaper, section: "Recommendations" },
  { id: "mood", label: "Mood Match", icon: Sparkles, section: "Discovery" },
  { id: "trending", label: "Trending", icon: TrendingUp, section: "Discovery" },
  { id: "browse", label: "Browse & Search", icon: Search, section: "Discovery" },
  { id: "world-cinema", label: "World Cinema", icon: Globe, section: "Discovery" },
  { id: "collections", label: "Collections", icon: Layers, section: "Discovery" },
  { id: "group", label: "Group Night", icon: Users, section: "Discovery" },
  { id: "watchlist", label: "Watchlist", icon: Bookmark, section: "Discovery" },
  { id: "import", label: "List Import", icon: Upload, section: "Discovery" },
  { id: "pulse", label: "Cultural Pulse", icon: Activity, section: "Discovery" },
  { id: "calendar", label: "Coming Soon", icon: CalendarDays, section: "Discovery" },
  { id: "notifications", label: "Notifications", icon: Bell, section: "Profile" },
  { id: "profile", label: "Taste Profile", icon: Heart, section: "Profile" },
  { id: "wrapped", label: "Plex Wrapped", icon: BarChart3, section: "Profile" },
  { id: "compare", label: "Taste Radar", icon: GitCompare, section: "Profile" },
  { id: "social", label: "Social", icon: Users, section: "Profile" },
  { id: "history", label: "Rec History", icon: History, section: "Profile" },
  { id: "library-health", label: "Library Health", icon: HeartPulse, section: "Library" },
  { id: "admin", label: "System Settings", icon: Settings, section: "Admin" },
];

export default navItems;

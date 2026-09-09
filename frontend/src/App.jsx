import { Routes, Route } from "react-router-dom";
import Header from "./components/Header";
import Footer from "./components/Footer";
import CookieBanner from "./components/CookieBanner";
import Home from "./pages/student/Home";
import Browse from "./pages/student/Browse";
import Subjects from "./pages/student/Subjects";
import PaperDetails from "./pages/student/PaperDetails";
import Privacy from "./pages/Privacy";
import Login from "./pages/admin/Login";
import AdminLayout from "./pages/admin/AdminLayout";
import Dashboard from "./pages/admin/Dashboard";
import Import from "./pages/admin/Import";
import ReviewQueue from "./pages/admin/ReviewQueue";
import Catalog from "./pages/admin/Catalog";
import AdminUsers from "./pages/admin/AdminUsers";

function StudentLayout({ children }) {
  return (
    <>
      <Header />
      <div className="page-container">{children}</div>
      <Footer />
    </>
  );
}

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<StudentLayout><Home /></StudentLayout>} />
        <Route path="/papers" element={<StudentLayout><Browse /></StudentLayout>} />
        <Route path="/subjects" element={<StudentLayout><Subjects /></StudentLayout>} />
        <Route path="/papers/:id" element={<StudentLayout><PaperDetails /></StudentLayout>} />
        <Route path="/privacy" element={<StudentLayout><Privacy /></StudentLayout>} />

        <Route path="/admin/login" element={<Login />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="import" element={<Import />} />
          <Route path="review" element={<ReviewQueue />} />
          <Route path="catalog" element={<Catalog />} />
          <Route path="users" element={<AdminUsers />} />
        </Route>
      </Routes>
      <CookieBanner />
    </>
  );
}

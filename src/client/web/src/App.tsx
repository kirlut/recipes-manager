import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { ProductDetail } from "./pages/products/ProductDetail";
import { ProductForm } from "./pages/products/ProductForm";
import { ProductsList } from "./pages/products/ProductsList";
import { RecipeDetail } from "./pages/recipes/RecipeDetail";
import { RecipeForm } from "./pages/recipes/RecipeForm";
import { RecipesList } from "./pages/recipes/RecipesList";
import { ShoppingListPage } from "./pages/shopping-list/ShoppingListPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Navigate to="/products" replace />
          </RequireAuth>
        }
      />
      <Route
        path="/products"
        element={
          <RequireAuth>
            <Layout>
              <ProductsList />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/products/new"
        element={
          <RequireAuth>
            <Layout>
              <ProductForm mode="create" />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/products/:id"
        element={
          <RequireAuth>
            <Layout>
              <ProductDetail />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/products/:id/edit"
        element={
          <RequireAuth>
            <Layout>
              <ProductForm mode="edit" />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/recipes"
        element={
          <RequireAuth>
            <Layout>
              <RecipesList />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/recipes/new"
        element={
          <RequireAuth>
            <Layout>
              <RecipeForm mode="create" />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/recipes/:id"
        element={
          <RequireAuth>
            <Layout>
              <RecipeDetail />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/recipes/:id/edit"
        element={
          <RequireAuth>
            <Layout>
              <RecipeForm mode="edit" />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/shopping-list"
        element={
          <RequireAuth>
            <Layout>
              <ShoppingListPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="*"
        element={
          <RequireAuth>
            <Layout>
              <div className="opacity-70 italic">Page not found.</div>
            </Layout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}

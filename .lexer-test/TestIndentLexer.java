import com.intellij.lexer.Lexer;
import com.intellij.lexer.MergingLexerAdapter;
import com.intellij.openapi.Disposable;
import com.intellij.openapi.application.Application;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.components.ComponentManager;
import com.intellij.openapi.extensions.ExtensionPoint;
import com.intellij.openapi.extensions.Extensions;
import com.intellij.openapi.extensions.impl.ExtensionsAreaImpl;
import com.intellij.psi.tree.IElementType;
import com.intellij.psi.tree.TokenSet;
import com.jetbrains.python.PyTokenTypes;
import com.jetbrains.python.PythonDialectsTokenSetContributor;
import com.jetbrains.python.PythonDialectsTokenSetProvider;
import com.jetbrains.python.lexer.PythonIndentingLexer;
import com.starnotesxj.sageide.parser.SageCaretLexer;
import kotlin.jvm.functions.Function0;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

/**
 * Reproduces the REAL production lexer chain:
 * PythonIndentingLexer -> MergingLexerAdapter(XOR) -> SageCaretLexer,
 * by faking the Application and extension-point area the Python lexer needs.
 */
public class TestIndentLexer {

  public static void main(String[] args) throws Exception {
    ComponentManager fakeManager = (ComponentManager)Proxy.newProxyInstance(
      ComponentManager.class.getClassLoader(),
      new Class<?>[]{ComponentManager.class},
      (proxy, method, a) -> {
        if (method.getName().equals("toString")) return "FakeComponentManager";
        if (method.getName().equals("hashCode")) return 0;
        if (method.getName().equals("equals")) return proxy == a[0];
        Class<?> rt = method.getReturnType();
        if (rt == boolean.class) return false;
        if (rt == int.class) return 0;
        if (rt == long.class) return 0L;
        return null;
      });
    ExtensionsAreaImpl area = new ExtensionsAreaImpl(fakeManager);
    Extensions.setRootArea(area);
    Disposable fakeDisposable = (Disposable)Proxy.newProxyInstance(
      Disposable.class.getClassLoader(),
      new Class<?>[]{Disposable.class},
      (proxy, method, a) -> null);
    area.registerExtensionPoint(
      PythonDialectsTokenSetContributor.EP_NAME,
      PythonDialectsTokenSetContributor.EP_NAME.getName(),
      ExtensionPoint.Kind.INTERFACE,
      fakeDisposable);
    final PythonDialectsTokenSetProvider provider = new PythonDialectsTokenSetProvider();

    Application fakeApp = (Application)Proxy.newProxyInstance(
      Application.class.getClassLoader(),
      new Class<?>[]{Application.class},
      new InvocationHandler() {
        @Override
        public Object invoke(Object proxy, Method method, Object[] a) {
          if (method.getName().equals("getService") && a.length == 1 &&
              a[0] == PythonDialectsTokenSetProvider.class) {
            return provider;
          }
          if (method.getName().equals("toString")) return "FakeApplication";
          if (method.getName().equals("hashCode")) return 0;
          if (method.getName().equals("equals")) return proxy == a[0];
          Class<?> rt = method.getReturnType();
          if (rt == boolean.class) return false;
          if (rt == int.class) return 0;
          if (rt == long.class) return 0L;
          return null;
        }
      });
    ApplicationManager.setApplication(fakeApp);

    String[] cases = {
      "m = 1\nn = 1\nm ^^=1\nprint(m)\n",
      "e ^^= b",
      "e^254",
      "x ^^ y",
      "x ^= y",
      "a = b ^^= c ^ d ^= e"
    };
    for (String text : cases) {
      System.out.println("=== " + text.replace("\n", "\\n"));
      dump(text);
    }
  }

  static void dump(String text) {
    SageCaretLexer lexer = new SageCaretLexer(new Function0<Lexer>() {
      @Override
      public Lexer invoke() {
        return new MergingLexerAdapter(new PythonIndentingLexer(), TokenSet.create(PyTokenTypes.XOR));
      }
    });
    lexer.start(text, 0, text.length(), 0);
    while (true) {
      IElementType t = lexer.getTokenType();
      if (t == null) break;
      int s = lexer.getTokenStart();
      int e = lexer.getTokenEnd();
      String tokText = text.substring(s, e).replace("\n", "\\n");
      System.out.println(String.format("  [%d-%d] %-24s '%s'", s, e, t, tokText));
      lexer.advance();
    }
  }
}
